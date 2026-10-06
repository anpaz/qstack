"""Discover and invoke independently packaged circuit-rule verifiers."""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from typing import Literal, Mapping, Protocol

from qstack.verification.model import Rule

Status = Literal["VERIFIED", "REFUTED", "UNSUPPORTED"]


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


class RuleBackend(Protocol):
    name: str

    def check(self, rule: Rule) -> RuleResult: ...


@dataclass(frozen=True)
class ExternalRuleBackend:
    """Adapter for an installed verifier of serialized circuit rules."""

    entry_point: EntryPoint

    @property
    def name(self) -> str:
        return self.entry_point.name

    def check(self, rule: Rule) -> RuleResult:
        try:
            payload = json.loads(json.dumps(asdict(rule), allow_nan=False))
            verdict = self.entry_point.load()(payload)
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
    """Discover third-party rule checkers without importing them into qstack."""
    return tuple(
        ExternalRuleBackend(point)
        for point in sorted(entry_points(group="qstack.rule_verifiers"), key=lambda point: point.name)
    )
