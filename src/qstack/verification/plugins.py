"""Discover and invoke independently packaged circuit-rule verifiers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from functools import cached_property
from importlib.metadata import EntryPoint, entry_points
from typing import Literal, Mapping, Protocol

from qstack.verification.model import CircuitRule

Status = Literal["VERIFIED", "REFUTED", "UNSUPPORTED"]
EncodingKind = Literal["identity", "stabilizer"]
_IDENTITY_ONLY = ("identity",)


@dataclass(frozen=True)
class BackendAttempt:
    """The outcome of invoking one verifier on a rule."""

    backend: str
    status: Status
    detail: str
    backend_version: str | None = None

    @classmethod
    def from_result(cls, result: RuleResult) -> BackendAttempt:
        return cls(result.backend, result.status, result.detail, result.backend_version)


@dataclass(frozen=True)
class RuleResult:
    rule: str
    backend: str
    status: Status
    detail: str
    raw_result: str | None = None
    backend_version: str | None = None
    configuration: dict[str, object] = field(default_factory=dict)
    sites: tuple[str, ...] = ()
    attempts: tuple[BackendAttempt, ...] | None = None


class RuleBackend(Protocol):
    """A circuit checker with an optional `supported_encodings` tuple."""

    name: str

    def check(self, rule: CircuitRule) -> RuleResult: ...


def supports_encoding(backend: RuleBackend, encoding: EncodingKind) -> bool:
    supported = getattr(backend, "supported_encodings", _IDENTITY_ONLY)
    return isinstance(supported, tuple) and encoding in supported


@dataclass(frozen=True)
class ExternalRuleBackend:
    """Adapter for an installed verifier of serialized circuit rules."""

    entry_point: EntryPoint

    @property
    def name(self) -> str:
        return self.entry_point.name

    @cached_property
    def _checker(self):
        return self.entry_point.load()

    @cached_property
    def supported_encodings(self) -> tuple[EncodingKind, ...]:
        try:
            supported = getattr(self._checker, "supported_encodings", _IDENTITY_ONLY)
        except Exception:
            # Let ordinary requests surface the load error through check().
            return _IDENTITY_ONLY
        return supported if isinstance(supported, tuple) else ()

    def check(self, rule: CircuitRule) -> RuleResult:
        try:
            encoding_kind = "identity" if rule.encoding.is_identity else "stabilizer"
            if not supports_encoding(self, encoding_kind):
                return RuleResult(
                    rule.id, self.name, "UNSUPPORTED", f"backend does not support {encoding_kind} encodings"
                )
            data = asdict(rule)
            if rule.encoding.is_identity:
                # Preserve the existing plugin payload for ordinary rules.
                del data["encoding"]
            payload = json.loads(json.dumps(data, allow_nan=False))
            verdict = self._checker(payload)
            if not isinstance(verdict, Mapping):
                raise ValueError("verifier did not return a verdict mapping")
            if verdict.get("rule") != rule.id:
                raise ValueError("verifier returned a verdict for a different rule")
            status = verdict.get("status")
            if status not in ("VERIFIED", "REFUTED", "UNSUPPORTED"):
                raise ValueError(f"invalid verifier status {status!r}")
            detail = verdict.get("detail")
            if not isinstance(detail, str):
                raise ValueError("verifier verdict has no detail string")
            configuration = verdict.get("configuration", {})
            if not isinstance(configuration, dict):
                raise ValueError("verifier configuration is not a dictionary")
            raw_result = verdict.get("raw_result")
            backend_version = verdict.get("backend_version")
            if raw_result is not None and not isinstance(raw_result, str):
                raise ValueError("verifier raw result is not a string")
            if backend_version is not None and not isinstance(backend_version, str):
                raise ValueError("verifier version is not a string")
            json.dumps(verdict, allow_nan=False)
            return RuleResult(rule.id, self.name, status, detail, raw_result, backend_version, configuration)
        except Exception as exc:
            return RuleResult(rule.id, self.name, "UNSUPPORTED", f"external verifier failed: {exc}")


def installed_rule_backends() -> tuple[ExternalRuleBackend, ...]:
    """Discover all installed rule checkers without loading the entry points."""
    return tuple(
        ExternalRuleBackend(point)
        for point in sorted(entry_points(group="qstack.rule_verifiers"), key=lambda point: point.name)
    )
