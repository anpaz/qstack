"""Check each reusable rule independently of its occurrence sites."""

from __future__ import annotations

from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr

from qstack.dialect.core import KernelOp
from qstack.verification.model import CircuitRule, Rule, ValueRef
from qstack.verification.patterns import extract_pattern, pattern_circuit
from qstack.verification.plugins import RuleResult
from qstack.verification.witness_check import _callback_sources


def check_structural_rule(rule: Rule, source: ModuleOp) -> RuleResult | CircuitRule:
    """Syntactic rules are built in; only gate rules go to circuit backends."""
    def verdict(status, detail):
        return RuleResult(rule.id, "structural", status, detail)

    if rule.kind == "identity":
        if rule.callee is not None or rule.source != rule.target or len(rule.source.operations) != 1:
            return verdict("REFUTED", "identity rule must pair the same single operation")
        return verdict("VERIFIED", "identical operation graphs")
    if rule.kind == "gate":
        if rule.callee is not None or not rule.source.operations:
            return verdict("REFUTED", "gate rule requires a nonempty source and no callee")
        try:
            old, new = pattern_circuit(rule.source), pattern_circuit(rule.target)
            if old.width != new.width:
                raise ValueError("gate rule changes its boundary width")
            return CircuitRule(rule.id, old, new)
        except ValueError as exc:
            return verdict("REFUTED", str(exc))
    if rule.kind == "inline":
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
            callee.body.block.args[callee.allocation_count:], body[-1].operands,
            tuple(range(callee.allocation_count)), _callback_sources(source),
        )
        if rule.target != expected:
            return verdict("REFUTED", "inline target is not an exact copy of the source callee")
        return verdict("VERIFIED", "exact source-callee graph substitution")
    return verdict("UNSUPPORTED", f"unknown rule kind {rule.kind!r}")
