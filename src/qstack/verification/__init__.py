"""Independent verification and visualization of compilation steps."""

from qstack.verification.builder import witness_from_replacements
from qstack.verification.docket import generate_docket
from qstack.verification.model import (
    Circuit,
    CircuitRule,
    Claim,
    Edge,
    Gate,
    KernelBoundary,
    Pattern,
    PatternOp,
    Rule,
    ValueRef,
    Witness,
)
from qstack.verification.plugins import BackendAttempt, RuleResult, installed_rule_backends
from qstack.verification.verifier import VerificationReport, verify
from qstack.verification.witness_check import KernelResult

__all__ = [
    "BackendAttempt",
    "Circuit",
    "CircuitRule",
    "Claim",
    "Edge",
    "Gate",
    "KernelBoundary",
    "KernelResult",
    "Pattern",
    "PatternOp",
    "Rule",
    "RuleResult",
    "ValueRef",
    "VerificationReport",
    "Witness",
    "generate_docket",
    "installed_rule_backends",
    "verify",
    "witness_from_replacements",
]
