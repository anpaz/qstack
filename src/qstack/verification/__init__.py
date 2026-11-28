"""Independent verification of one qstack compilation result."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from qstack.compilation import ArtifactError, CompilationResult, load_artifact, module_text, parse_module
from qstack.verification.plugins import RuleBackend, RuleResult, Status, installed_rule_backends, supports_encoding
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
                rules.append(RuleResult(**rule))
            kernels = tuple(KernelResult(**kernel) for kernel in data.pop("kernels", []))
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
    the whole step. For IR validation, use :func:`qstack.validation.validate_module`.
    """
    if result.artifact_path is None:
        return VerificationReport("UNSUPPORTED", "result has no compilation step artifact", None)
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
        return VerificationReport("REFUTED", str(exc), artifact_path, artifact_sha256=artifact_sha256)
    if artifact.witness is None:
        return VerificationReport(
            "UNSUPPORTED", "compiler emitted no witness", artifact_path, artifact_sha256=artifact_sha256,
        )
    kernels: list[KernelResult] = []
    try:
        check_witness_structure(source, target, artifact.witness, record_kernel=kernels.append)
    except UnsupportedWitnessError as exc:
        return VerificationReport(
            "UNSUPPORTED", str(exc), artifact_path,
            kernels=tuple(kernels), artifact_sha256=artifact_sha256,
        )
    except WitnessError as exc:
        logger.debug("artifact %s witness structure refuted: %s", artifact_path, exc)
        return VerificationReport(
            "REFUTED", str(exc), artifact_path,
            kernels=tuple(kernels), artifact_sha256=artifact_sha256,
        )
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        logger.debug("artifact %s has a malformed witness: %s", artifact_path, exc)
        return VerificationReport(
            "REFUTED", f"malformed witness: {exc}", artifact_path,
            kernels=tuple(kernels), artifact_sha256=artifact_sha256,
        )

    encoding = artifact.witness.encoding
    encoding_kind = "identity" if encoding.is_identity else "stabilizer"
    configured = tuple(backends) if backends is not None else installed_rule_backends()
    results: list[RuleResult] = []
    for rule in artifact.witness.rules:
        sites = tuple(claim.id for claim in artifact.witness.claims if claim.rule == rule.id)
        checked_rule = check_structural_rule(rule, source, encoding)
        if isinstance(checked_rule, RuleResult):
            outcome = RuleResult(
                checked_rule.rule, checked_rule.backend, checked_rule.status, checked_rule.detail,
                sites=sites,
            )
        else:
            outcome = RuleResult(
                rule.id, "none", "UNSUPPORTED",
                f"no configured rule backend supports {encoding_kind} encodings", sites=sites,
            )
            for backend in configured:
                if not supports_encoding(backend, encoding_kind):
                    continue
                checked = backend.check(checked_rule)
                outcome = RuleResult(
                    checked.rule, checked.backend, checked.status, checked.detail,
                    checked.raw_result, checked.backend_version, checked.configuration, sites,
                )
                logger.debug("rule %s at %s: %s %s", rule.id, sites, outcome.status, outcome.detail)
                if outcome.status != "UNSUPPORTED":
                    break
        results.append(outcome)
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
    return VerificationReport(status, detail, artifact_path, tuple(results), tuple(kernels), artifact_sha256)


__all__ = [
    "Circuit", "CircuitRule", "Claim", "Edge", "Gate", "KernelBoundary", "KernelResult", "Pattern", "PatternOp",
    "Rule", "RuleResult", "ValueRef", "VerificationReport",
    "Witness", "installed_rule_backends", "verify",
    "witness_from_replacements",
]
