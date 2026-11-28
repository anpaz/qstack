"""Check each reusable rule independently of its occurrence sites."""

from __future__ import annotations

from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr

from qstack.dialect.core import KernelOp
from qstack.encoding import Encoding
from qstack.verification.model import CircuitRule, Rule, ValueRef
from qstack.verification.patterns import extract_pattern, has_qubits, pattern_circuit
from qstack.verification.plugins import RuleResult
from qstack.verification.witness_check import _callback_sources


def check_structural_rule(rule: Rule, source: ModuleOp, encoding: Encoding) -> RuleResult | CircuitRule:
    """Syntactic rules are built in; only gate rules go to circuit backends."""
    def verdict(status, detail):
        return RuleResult(rule.id, "structural", status, detail)

    if rule.kind == "identity":
        if rule.callee is not None or rule.source != rule.target or len(rule.source.operations) != 1:
            return verdict("REFUTED", "identity rule must pair the same single operation")
        if not encoding.is_identity and has_qubits(rule.source):
            return verdict("REFUTED", "a qubit operation under a nonidentity encoding requires a semantic rule or widening")
        return verdict("VERIFIED", "identical operation graphs")
    if rule.kind == "gate":
        if rule.callee is not None or not rule.source.operations:
            return verdict("REFUTED", "gate rule requires a nonempty source and no callee")
        try:
            old, new = pattern_circuit(rule.source), pattern_circuit(rule.target)
            if new.width != old.width * encoding.physical_qubits:
                raise ValueError("gate boundary disagrees with the declared encoding width")
            return CircuitRule(rule.id, old, new, encoding)
        except ValueError as exc:
            return verdict("REFUTED", str(exc))
    if rule.kind == "unsupported":
        return verdict("UNSUPPORTED", "no rule verifier supports this rewrite shape")
    if rule.kind in ("allocation", "measurement", "widening"):
        return verdict("UNSUPPORTED", f"{rule.kind} rule check is not implemented")
    if rule.kind == "inline":
        if not encoding.is_identity:
            return verdict("REFUTED", "an inline rule requires the identity encoding")
        kernels = {op.sym_name.data: op for op in source.body.ops if isinstance(op, KernelOp)}
        callee = kernels.get(rule.callee)
        if callee is None or len(rule.source.operations) != 1:
            return verdict("REFUTED", "inline rule must name a source callee and replace one call")
        call = rule.source.operations[0]
        if (
            call.name != "qstack.call"
            or dict(call.properties).get("callee") != str(SymbolRefAttr(rule.callee))
            or rule.source.inputs != tuple(str(typ) for typ in callee.input_types)
            or call.operands != tuple(ValueRef("arg", i) for i in range(len(callee.input_types)))
            or call.result_types != tuple(str(typ) for typ in callee.declared_result_types)
            or rule.source.outputs != tuple(ValueRef("result", 0, i) for i in range(len(call.result_types)))
        ):
            return verdict("REFUTED", "inline source does not match the callee's call interface")
        body = tuple(callee.body.block.ops)
        expected = extract_pattern(
            callee, tuple(range(len(body) - 1)),
            callee.body.block.args, body[-1].operands,
            _callback_sources(source),
        )
        if rule.target != expected:
            return verdict("REFUTED", "inline target is not an exact copy of the source callee")
        return verdict("VERIFIED", "exact source-callee graph substitution")
    return verdict("UNSUPPORTED", f"unknown rule kind {rule.kind!r}")
