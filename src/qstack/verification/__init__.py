"""Independent verification of one qstack compilation result."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Sequence

from qstack.compilation import ArtifactError, CompilationResult, load_artifact, module_text, parse_module
from qstack.verification.plugins import (
    BackendAttempt, RuleBackend, RuleResult, Status, installed_rule_backends, supports_encoding,
)
from qstack.verification.builder import witness_from_replacements
from qstack.verification.witness_check import (
    KernelResult, UnsupportedWitnessError, WitnessError, check_witness_structure,
)
from qstack.verification.model import (
    Circuit, CircuitRule, Claim, Edge, Gate, KernelBoundary,
    Pattern, PatternOp, Rule, ValueRef, Witness,
)
from qstack.verification.rules import check_structural_rule

logger = logging.getLogger("qstack.verification")


@dataclass(frozen=True)
class VerificationReport:
    status: Status
    detail: str
    artifact_path: str | None
    rules: tuple[RuleResult, ...] = ()
    kernels: tuple[KernelResult, ...] = ()
    artifact_sha256: str | None = None
    available_backends: tuple[str, ...] | None = None

    @property
    def backends_used(self) -> tuple[tuple[str, str | None], ...]:
        """Return the recorded rule backends and their known versions."""
        backends: dict[tuple[str, str | None], None] = {}
        for rule in self.rules:
            if rule.attempts is not None:
                backends.update(dict.fromkeys((attempt.backend, attempt.backend_version) for attempt in rule.attempts))
            elif rule.backend != "none":
                backends[rule.backend, rule.backend_version] = None
        versioned = {name for name, version in backends if version is not None}
        return tuple((name, version) for name, version in backends if version is not None or name not in versioned)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> VerificationReport:
        """Read a verification report written by :meth:`save`."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            rules = []
            for rule in data.pop("rules", []):
                rule["sites"] = tuple(rule.get("sites", ()))
                attempts = rule.get("attempts")
                if attempts is not None:
                    rule["attempts"] = tuple(BackendAttempt(**attempt) for attempt in attempts)
                rules.append(RuleResult(**rule))
            kernels = tuple(KernelResult(**kernel) for kernel in data.pop("kernels", []))
            if data.get("available_backends") is not None:
                data["available_backends"] = tuple(data["available_backends"])
            return cls(**data, rules=tuple(rules), kernels=kernels)
        except (TypeError, AttributeError, ValueError) as exc:
            raise ValueError(f"malformed verification report {path}") from exc


def verify(
    result: CompilationResult,
    *,
    backends: Sequence[RuleBackend] | None = None,
) -> VerificationReport:
    """Check the compiler step represented by ``result`` against its witness.

    Kernel verdicts describe claim-graph structure and expansion. Rule verdicts
    describe the local semantics checks, and the overall verdict applies to
    the whole step. The report records installed backends and any explicit
    backends supplied for this run. For IR validation, use
    :func:`qstack.validation.validate_module`.
    """
    installed = installed_rule_backends()
    configured = installed if backends is None else tuple(backends)
    backend_names = ["structural", *(backend.name for backend in installed)]
    if backends is not None:
        backend_names.extend(
            name for backend in configured if (name := getattr(backend, "name", None))
        )
    available_backends = tuple(dict.fromkeys(backend_names))

    if result.artifact_path is None:
        return VerificationReport(
            "UNSUPPORTED", "result has no compilation step artifact", None,
            available_backends=available_backends,
        )
    artifact_path = str(result.artifact_path)
    artifact_sha256 = None
    try:
        artifact = load_artifact(result.artifact_path)
        artifact_sha256 = artifact.fingerprint()
        if module_text(result.module) != artifact.target:
            raise ArtifactError("result module differs from recorded target IR")
        if result.witness != artifact.witness:
            raise ArtifactError("result witness differs from recorded witness")
        source = parse_module(artifact.source)
        target = parse_module(artifact.target)
    except Exception as exc:
        logger.debug("artifact %s rejected: %s", artifact_path, exc)
        return VerificationReport(
            "REFUTED", str(exc), artifact_path,
            artifact_sha256=artifact_sha256, available_backends=available_backends,
        )
    if artifact.witness is None:
        return VerificationReport(
            "UNSUPPORTED", "compiler emitted no witness", artifact_path,
            artifact_sha256=artifact_sha256, available_backends=available_backends,
        )
    kernels: list[KernelResult] = []
    try:
        check_witness_structure(source, target, artifact.witness, record_kernel=kernels.append)
    except UnsupportedWitnessError as exc:
        return VerificationReport(
            "UNSUPPORTED", str(exc), artifact_path,
            kernels=tuple(kernels), artifact_sha256=artifact_sha256,
            available_backends=available_backends,
        )
    except WitnessError as exc:
        logger.debug("artifact %s witness structure refuted: %s", artifact_path, exc)
        return VerificationReport(
            "REFUTED", str(exc), artifact_path,
            kernels=tuple(kernels), artifact_sha256=artifact_sha256,
            available_backends=available_backends,
        )
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        logger.debug("artifact %s has a malformed witness: %s", artifact_path, exc)
        return VerificationReport(
            "REFUTED", f"malformed witness: {exc}", artifact_path,
            kernels=tuple(kernels), artifact_sha256=artifact_sha256,
            available_backends=available_backends,
        )

    encoding = artifact.witness.encoding
    encoding_kind = "identity" if encoding.is_identity else "stabilizer"
    results: list[RuleResult] = []
    for rule in artifact.witness.rules:
        sites = tuple(claim.id for claim in artifact.witness.claims if claim.rule == rule.id)
        checked_rule = check_structural_rule(rule, source, encoding)
        attempts: list[BackendAttempt] = []
        if isinstance(checked_rule, RuleResult):
            outcome = checked_rule
            attempts.append(BackendAttempt.from_result(outcome))
        else:
            outcome = RuleResult(
                rule.id, "none", "UNSUPPORTED",
                f"no configured rule backend supports {encoding_kind} encodings",
            )
            for backend in configured:
                if not supports_encoding(backend, encoding_kind):
                    continue
                outcome = backend.check(checked_rule)
                attempts.append(BackendAttempt.from_result(outcome))
                logger.debug("rule %s at %s: %s %s", rule.id, sites, outcome.status, outcome.detail)
                if outcome.status != "UNSUPPORTED":
                    break
        results.append(replace(outcome, sites=sites, attempts=tuple(attempts)))
    if any(item.status == "REFUTED" for item in results):
        status: Status = "REFUTED"
        detail = "one or more rules were refuted"
    elif any(item.status == "UNSUPPORTED" for item in results):
        status = "UNSUPPORTED"
        detail = "one or more rules could not be checked"
    elif not encoding.is_identity:
        status = "UNSUPPORTED"
        detail = "only individual encoded gate rules are currently verified"
    else:
        status = "VERIFIED"
        detail = "claim graphs and rules verified"
    return VerificationReport(
        status, detail, artifact_path, tuple(results), tuple(kernels), artifact_sha256,
        available_backends=available_backends,
    )


__all__ = [
    "BackendAttempt", "Circuit", "CircuitRule", "Claim", "Edge", "Gate", "KernelBoundary", "KernelResult", "Pattern", "PatternOp",
    "Rule", "RuleResult", "ValueRef", "VerificationReport",
    "Witness", "installed_rule_backends", "verify",
    "witness_from_replacements",
]
