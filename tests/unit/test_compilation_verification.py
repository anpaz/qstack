"""Independent claim-graph validation and reusable rule checks."""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import replace
from types import SimpleNamespace

import pytest
from xdsl.dialects.builtin import ModuleOp, StringAttr
from xdsl.ir import Block, Region

from qstack.compilation import CompilationResult
from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import HOp, XOp
from qstack.dialect.core import AllocOp, DecodeOp, DecoderOp, KernelOp, MeasureOp, ReturnOp
from qstack.dialect.h2 import U1Op
from qstack.encoding import Encoding
from qstack.passes.contracts import Replacement
from qstack.passes.clifford_peephole import CliffordPeepholeOptimization
from qstack.passes.cliffords2atoms import CliffordsToAtomsLowering
from qstack.passes.cliffords2h2 import CliffordsToH2Lowering
from qstack.surface import compile_qasm
from qstack.verification import (
    Circuit, CircuitRule, Claim, Edge, KernelBoundary, Rule, ValueRef, VerificationReport, Witness,
    installed_rule_backends, verify, witness_from_replacements,
)
from qstack.verification.plugins import ExternalRuleBackend
from qstack.verification.viewer import generate_docket
from qstack.verification.witness_check import _KernelSide, _callback_sources, _pattern_at
import qstack.verification.plugins as rule_backends


def _matrix_backend():
    for backend in installed_rule_backends():
        if backend.name == "matrix":
            return backend
    pytest.skip("install the independent quivalence distribution")


def _program(gates):
    block = Block()
    allocation = AllocOp()
    block.add_op(allocation)
    wire = allocation.result
    instances = []
    for constructor in gates:
        gate = constructor(wire)
        block.add_op(gate)
        instances.append(gate)
        wire = gate.results[0]
    measure = MeasureOp(operand=wire)
    block.add_ops([measure, ReturnOp(operands=[measure.result])])
    return ModuleOp([KernelOp("main", input_types=[], result_types=[BitType()], region=Region([block]))]), instances


def _bind(source, target, claims, edges, kinds):
    """Build explicit rule patterns for deliberately constructed test sites."""
    old = {k.sym_name.data: _KernelSide(k) for k in source.body.ops if isinstance(k, KernelOp)}
    new = {k.sym_name.data: _KernelSide(k) for k in target.body.ops if isinstance(k, KernelOp)}
    edge_map = {edge.id: edge for edge in edges}
    rules = {}
    for claim in claims:
        rule = Rule(
            claim.rule,
            _pattern_at(claim, old[claim.kernel], edge_map, "source", _callback_sources(source)),
            _pattern_at(claim, new[claim.kernel], edge_map, "target", _callback_sources(target)),
            kinds[claim.rule],
        )
        if claim.rule in rules:
            assert rules[claim.rule] == rule
        rules[claim.rule] = rule
    return Witness.bind(source, target, rules=tuple(rules.values()), claims=tuple(claims), edges=tuple(edges), kernels=tuple(KernelBoundary(name, ()) for name in old))


def _witness(source, target, old_gates, new_gates):
    # Operation 0 is the allocation; the gates follow it.
    sm, tm = len(old_gates), len(new_gates)
    edges = (
        Edge("input", "main", (ValueRef("result", 0),), (ValueRef("result", 0),)),
        Edge("output", "main", (ValueRef("result", sm),), (ValueRef("result", tm),)),
        Edge("bit", "main", (ValueRef("result", sm + 1),), (ValueRef("result", tm + 1),)),
    )
    claims = (
        Claim("allocation", "main", "alloc", (0,), (0,), (), ("input",)),
        Claim("site", "main", "rewrite", tuple(range(1, sm + 1)), tuple(range(1, tm + 1)), ("input",), ("output",)),
        Claim("measure", "main", "measure", (sm + 1,), (tm + 1,), ("output",), ("bit",)),
        Claim("return", "main", "return", (sm + 2,), (tm + 2,), ("bit",), ()),
    )
    return _bind(source, target, claims, edges, {"alloc": "identity", "rewrite": "gate", "measure": "identity", "return": "identity"})


def _result(source, target, witness, tmp_path):
    return CompilationResult.from_step(CompilationResult.from_module(source), target, witness, artifact_path=tmp_path / "step.json")


def test_external_rule_backend_receives_only_circuits():
    received = []
    def check(payload):
        received.append(payload)
        return {"rule": payload["id"], "status": "VERIFIED", "detail": "checked"}
    backend = ExternalRuleBackend(SimpleNamespace(name="stub", load=lambda: check))
    assert backend.check(CircuitRule("empty", Circuit(0, ()), Circuit(0, ()))).status == "VERIFIED"
    assert received == [{"id": "empty", "source": {"width": 0, "gates": []}, "target": {"width": 0, "gates": []}}]


def test_external_rule_backend_rejects_bad_verdict():
    backend = ExternalRuleBackend(SimpleNamespace(name="stub", load=lambda: lambda _: {"rule": "wrong", "status": "VERIFIED", "detail": "checked"}))
    assert backend.check(CircuitRule("expected", Circuit(0, ()), Circuit(0, ()))).status == "UNSUPPORTED"


def test_rule_backend_discovery_allows_no_external_install(monkeypatch):
    monkeypatch.setattr(rule_backends, "entry_points", lambda **_: ())
    assert installed_rule_backends() == ()


def test_compilation_result_has_only_latest_step(tmp_path):
    source = CompilationResult.from_module(compile_qasm('QSTACKQASM 0.1; include "qstack/cliffords.inc"; qubit[1] q; bit[1] c; h q[0]; measure q[0] -> c[0];'))
    assert source.witness is None
    target, _ = _program([])
    first = CompilationResult.from_step(source, target, artifact_path=tmp_path / "first.json")
    assert verify(first).status == "UNSUPPORTED"
    second = CompilationResult.from_step(first, source.module.clone(), artifact_path=tmp_path / "second.json")
    data = json.loads(second.artifact_path.read_text())
    assert data["version"] == 3
    assert data["source"] != data["target"]
    assert data["witness"] is None
    assert CompilationResult.load(second.artifact_path).artifact_path == second.artifact_path


def test_matrix_verifies_cancellation_and_saved_artifact(tmp_path):
    source, old = _program([HOp, HOp])
    target, new = _program([])
    result = _result(source, target, _witness(source, target, old, new), tmp_path)
    report = verify(result, backends=(_matrix_backend(),))
    assert report.status == "VERIFIED"
    assert next(rule for rule in report.rules if rule.rule == "rewrite").sites == ("site",)
    assert verify(CompilationResult.load(result.artifact_path), backends=(_matrix_backend(),)).status == "VERIFIED"
    report.save(tmp_path / "report.json")
    assert VerificationReport.load(tmp_path / "report.json") == report
    assert [(item.kernel, item.status) for item in report.kernels] == [("main", "VERIFIED")]


def test_thesis_example_has_four_rules_and_seven_claims():
    source = compile_qasm('QSTACKQASM 0.1; include "qstack/cliffords.inc"; qubit[2] q; bit[2] c; x q[0]; x q[1]; measure q[0] -> c[0]; measure q[1] -> c[1];')
    result = CliffordsToAtomsLowering().run(source)
    witness = result.witness
    assert len(witness.rules) == 4
    assert len(witness.claims) == 7
    assert {claim.rule for claim in witness.claims} == {rule.id for rule in witness.rules}
    gate_rule = next(rule for rule in witness.rules if rule.kind == "gate")
    assert sum(claim.rule == gate_rule.id for claim in witness.claims) == 2
    assert verify(result, backends=(_matrix_backend(),)).status == "VERIFIED"


def test_repeated_sites_check_each_rule_once():
    source, _ = _program([HOp, HOp, HOp, HOp])
    result = CliffordPeepholeOptimization().run(CompilationResult.from_module(source))
    backend = _matrix_backend()
    calls = []
    class CountingBackend:
        def check(self, rule):
            calls.append(rule.id)
            return backend.check(rule)
    report = verify(result, backends=(CountingBackend(),))
    assert report.status == "VERIFIED"
    assert len(result.witness.rules) == 4
    assert len(calls) == 1
    assert len(next(rule for rule in report.rules if rule.backend == "matrix").sites) == 2


def test_frontend_peephole_witness_round_trips_and_verifies(tmp_path):
    source = compile_qasm('QSTACKQASM 0.1; include "qstack/cliffords.inc"; qubit[1] q; bit[1] c; h q[0]; h q[0]; s q[0]; s q[0]; measure q[0] -> c[0];')
    result = CliffordPeepholeOptimization().run(source).save(tmp_path / "peephole.json")
    assert len(result.witness.rules) == 5
    assert verify(CompilationResult.load(result.artifact_path), backends=(_matrix_backend(),)).status == "VERIFIED"


def test_identity_rules_need_no_backend():
    source, _ = _program([XOp])
    result = CliffordPeepholeOptimization().run(CompilationResult.from_module(source))
    report = verify(result, backends=())
    assert report.status == "VERIFIED"
    assert all(rule.backend == "structural" for rule in report.rules)


def test_gate_rules_without_backend_are_unsupported():
    source, _ = _program([HOp, HOp])
    result = CliffordPeepholeOptimization().run(CompilationResult.from_module(source))
    assert verify(result, backends=()).status == "UNSUPPORTED"


def test_matrix_accepts_global_phase(tmp_path):
    source, old = _program([XOp])
    target, new = _program([lambda wire: U1Op(wire, math.pi, 0)])
    report = verify(_result(source, target, _witness(source, target, old, new), tmp_path), backends=(_matrix_backend(),))
    assert report.status == "VERIFIED"


def test_h2_lowering_verifies_up_to_global_phase():
    source, _ = _program([XOp])
    assert verify(CliffordsToH2Lowering().run(CompilationResult.from_module(source)), backends=(_matrix_backend(),)).status == "VERIFIED"


def test_identity_rule_cannot_hide_changed_gate(tmp_path):
    source, old = _program([HOp])
    target, new = _program([XOp])
    witness = _witness(source, target, old, new)
    witness = replace(witness, rules=tuple(replace(rule, kind="identity") if rule.id == "rewrite" else rule for rule in witness.rules))
    report = verify(_result(source, target, witness, tmp_path), backends=())
    assert report.status == "REFUTED"
    assert "identity rule" in next(rule.detail for rule in report.rules if rule.rule == "rewrite")


@pytest.mark.parametrize("mutation", ["binding", "missing_rule", "missing_claim", "pattern", "duplicate_allocation", "unknown_kind"])
def test_false_or_unsupported_witnesses(tmp_path, mutation):
    source, old = _program([HOp, HOp])
    target, new = _program([])
    witness = _witness(source, target, old, new)
    if mutation == "binding":
        witness = replace(witness, claims=tuple(replace(claim, inputs=("bit",)) if claim.id == "site" else claim for claim in witness.claims))
    elif mutation == "missing_rule":
        witness = replace(witness, rules=witness.rules[1:])
    elif mutation == "missing_claim":
        witness = replace(witness, claims=witness.claims[:-1])
    elif mutation == "pattern":
        witness = replace(witness, rules=tuple(replace(rule, target=rule.source) if rule.id == "rewrite" else rule for rule in witness.rules))
    elif mutation == "duplicate_allocation":
        witness = replace(witness, claims=tuple(replace(claim, source_ops=(0, 0)) if claim.id == "allocation" else claim for claim in witness.claims))
    else:
        witness = replace(witness, rules=tuple(replace(rule, kind="future") if rule.id == "rewrite" else rule for rule in witness.rules))
    assert verify(_result(source, target, witness, tmp_path), backends=()).status == ("UNSUPPORTED" if mutation == "unknown_kind" else "REFUTED")


def test_tampered_artifact_is_rejected_before_rule_checks(tmp_path):
    source, old = _program([HOp, HOp])
    target, new = _program([])
    result = _result(source, target, _witness(source, target, old, new), tmp_path)
    payload = json.loads(result.artifact_path.read_text())
    payload["source"] += "\n"
    result.artifact_path.write_text(json.dumps(payload))
    assert "SHA-256" in verify(result).detail


def test_mutated_returned_module_does_not_match_its_artifact(tmp_path):
    source, old = _program([HOp, HOp])
    target, new = _program([])
    result = _result(source, target, _witness(source, target, old, new), tmp_path)
    result.module.attributes["tampered"] = StringAttr("yes")
    assert "result module differs" in verify(result).detail


@pytest.mark.parametrize("separate_sources", [False, True])
def test_callback_host_wire_order_is_checked(tmp_path, separate_sources):
    names = ("a.1:decode", "b.2:decode") if separate_sources else ("a", "b")
    def module(reverse):
        block = Block()
        a = [AllocOp(), AllocOp()]
        m = [MeasureOp(operand=op.result) for op in a]
        d = [DecodeOp(callee=name, bit_operands=[op.result]) for name, op in zip(names, m)]
        block.add_ops([*a, *m, *(reversed(d) if reverse else d), ReturnOp(operands=[op.result for op in d])])
        return ModuleOp([*(DecoderOp(name, 1) for name in names), KernelOp("main", input_types=[], result_types=[BitType(), BitType()], region=Region([block]))])
    source, target = module(False), module(True)
    # Operations: two allocations, two measurements, two decodes (reversed in the target), return.
    edges = tuple(Edge(f"q{i}", "main", (ValueRef("result", i),), (ValueRef("result", i),)) for i in range(2)) + tuple(Edge(f"m{i}", "main", (ValueRef("result", i + 2),), (ValueRef("result", i + 2),)) for i in range(2)) + tuple(Edge(f"d{i}", "main", (ValueRef("result", i + 4),), (ValueRef("result", 5 - i),)) for i in range(2))
    claims = tuple(Claim(f"alloc{i}", "main", "alloc", (i,), (i,), (), (f"q{i}",)) for i in range(2)) + tuple(Claim(f"m{i}", "main", "measure", (i + 2,), (i + 2,), (f"q{i}",), (f"m{i}",)) for i in range(2)) + tuple(Claim(f"d{i}", "main", f"decode{i}", (i + 4,), (5 - i,), (f"m{i}",), (f"d{i}",)) for i in range(2)) + (Claim("return", "main", "return", (6,), (6,), ("d0", "d1"), ()),)
    witness = _bind(source, target, claims, edges, {name: "identity" for name in ("alloc", "measure", "decode0", "decode1", "return")})
    report = verify(_result(source, target, witness, tmp_path), backends=())
    assert report.status == ("VERIFIED" if separate_sources else "REFUTED")
    if not separate_sources:
        assert "host-wire order" in report.detail


def test_locally_convex_claims_can_still_form_a_global_cycle(tmp_path):
    block = Block()
    q0, q1 = AllocOp(), AllocOp()
    a0, b0 = HOp(q0.result), XOp(q1.result)
    a1, b1 = HOp(a0.result), XOp(b0.result)
    ma, mb = MeasureOp(operand=a1.result), MeasureOp(operand=b1.result)
    block.add_ops([q0, q1, a0, b0, a1, b1, ma, mb, ReturnOp(operands=[ma.result, mb.result])])
    source = ModuleOp([KernelOp("main", input_types=[], result_types=[BitType(), BitType()], region=Region([block]))])
    target = source.clone()
    # r0..r5 are the results of the gates and measurements, operations 2..7.
    refs = {"q0": ValueRef("result", 0), "q1": ValueRef("result", 1), **{f"r{i}": ValueRef("result", i + 2) for i in range(6)}}
    edges = tuple(Edge(name, "main", (ref,), (ref,)) for name, ref in refs.items())
    claims = (
        Claim("alloc0", "main", "alloc", (0,), (0,), (), ("q0",)),
        Claim("alloc1", "main", "alloc", (1,), (1,), (), ("q1",)),
        Claim("A", "main", "A", (2, 5), (2, 5), ("q0", "r1"), ("r0", "r3")),
        Claim("B", "main", "B", (3, 4), (3, 4), ("q1", "r0"), ("r1", "r2")),
        Claim("ma", "main", "measure", (6,), (6,), ("r2",), ("r4",)),
        Claim("mb", "main", "measure", (7,), (7,), ("r3",), ("r5",)),
        Claim("return", "main", "return", (8,), (8,), ("r4", "r5"), ()),
    )
    witness = _bind(source, target, claims, edges, {"alloc": "identity", "A": "gate", "B": "gate", "measure": "identity", "return": "identity"})
    report = verify(_result(source, target, witness, tmp_path), backends=())
    assert report.status == "REFUTED"
    assert "claim graph is cyclic" in report.detail
    assert [(item.kernel, item.status) for item in report.kernels] == [("main", "REFUTED")]
    assert not report.rules


def test_graph_patterns_ignore_independent_gate_order():
    def module(reverse):
        block = Block()
        q0, q1 = AllocOp(), AllocOp()
        h, x = HOp(q0.result), XOp(q1.result)
        ma, mb = MeasureOp(operand=h.result), MeasureOp(operand=x.result)
        block.add_ops([q0, q1, *([x, h] if reverse else [h, x]), ma, mb, ReturnOp(operands=[ma.result, mb.result])])
        return ModuleOp([KernelOp("main", input_types=[], result_types=[BitType(), BitType()], region=Region([block]))])
    source, target = module(False), module(True)
    old, new = next(iter(source.body.ops)), next(iter(target.body.ops))
    so, to = tuple(old.body.block.ops), tuple(new.body.block.ops)
    records = [Replacement((a,), (b,), (), ((a.result, b.result),)) for a, b in zip(so[:2], to[:2])]
    fresh = tuple((a.result, b.result) for a, b in zip(so[:2], to[:2]))
    records.append(Replacement(so[2:4], to[2:4], fresh, ((so[2].result, to[3].result), (so[3].result, to[2].result))))
    for a, b in zip(so[4:], to[4:]):
        records.append(Replacement((a,), (b,), tuple(zip(a.operands, b.operands)), tuple(zip(a.results, b.results))))
    witness = witness_from_replacements(source, target, {"main": records}, encoding=Encoding.identity())
    rule = next(rule for rule in witness.rules if rule.kind == "gate")
    assert rule.source == rule.target


def test_gate_rule_checks_output_permutations(tmp_path):
    from qstack.dialect.cliffords import CxOp
    old_allocs = [AllocOp(), AllocOp()]
    c0 = CxOp(*(op.result for op in old_allocs))
    c1 = CxOp(c0.results[1], c0.results[0])
    c2 = CxOp(c1.results[1], c1.results[0])
    old_measures = [MeasureOp(operand=q) for q in c2.results]
    old_block = Block()
    old_block.add_ops([*old_allocs, c0, c1, c2, *old_measures, ReturnOp(operands=[m.result for m in old_measures])])
    new_allocs = [AllocOp(), AllocOp()]
    new_measures = [MeasureOp(operand=op.result) for op in reversed(new_allocs)]
    new_block = Block()
    new_block.add_ops([*new_allocs, *new_measures, ReturnOp(operands=[m.result for m in new_measures])])
    def module(block):
        return ModuleOp([KernelOp("main", input_types=[], result_types=[BitType(), BitType()], region=Region([block]))])
    source, target = module(old_block), module(new_block)
    # Source: allocations 0-1, CX 2-4, measurements 5-6, return 7. Target: allocations 0-1, measurements 2-3, return 4.
    edges = tuple(Edge(f"i{i}", "main", (ValueRef("result", i),), (ValueRef("result", i),)) for i in range(2)) + tuple(Edge(f"o{i}", "main", (ValueRef("result", 4, i),), (ValueRef("result", 1 - i),)) for i in range(2)) + tuple(Edge(f"b{i}", "main", (ValueRef("result", 5 + i),), (ValueRef("result", 2 + i),)) for i in range(2))
    claims = tuple(Claim(f"alloc{i}", "main", "alloc", (i,), (i,), (), (f"i{i}",)) for i in range(2)) + (
        Claim("swap", "main", "swap", (2, 3, 4), (), ("i0", "i1"), ("o0", "o1")),
        Claim("m0", "main", "measure", (5,), (2,), ("o0",), ("b0",)),
        Claim("m1", "main", "measure", (6,), (3,), ("o1",), ("b1",)),
        Claim("return", "main", "return", (7,), (4,), ("b0", "b1"), ()),
    )
    witness = _bind(source, target, claims, edges, {"alloc": "identity", "swap": "gate", "measure": "identity", "return": "identity"})
    assert verify(_result(source, target, witness, tmp_path), backends=(_matrix_backend(),)).status == "VERIFIED"


def test_rules_cannot_change_gate_matrices_in_the_witness(tmp_path):
    source, old = _program([HOp])
    target, new = _program([XOp])
    witness = _witness(source, target, old, new)
    def corrupt(rule):
        if rule.id != "rewrite":
            return rule
        op = rule.target.operations[0]
        gate = replace(op.gate, matrix=rule.source.operations[0].gate.matrix)
        return replace(rule, target=replace(rule.target, operations=(replace(op, gate=gate),)))
    witness = replace(witness, rules=tuple(corrupt(rule) for rule in witness.rules))
    report = verify(_result(source, target, witness, tmp_path), backends=())
    assert report.status == "REFUTED"
    assert "site does not instantiate" in report.detail


def test_previous_artifact_schema_is_explicitly_rejected(tmp_path):
    source, old = _program([HOp, HOp])
    target, new = _program([])
    result = _result(source, target, _witness(source, target, old, new), tmp_path)
    payload = json.loads(result.artifact_path.read_text())
    payload["version"] = 2
    result.artifact_path.write_text(json.dumps(payload))
    report = verify(result)
    assert report.status == "REFUTED"
    assert "artifact version 2" in report.detail


@pytest.mark.skipif(shutil.which("dot") is None, reason="HTML graph export uses Graphviz")
def test_witness_report_overlays_only_matching_check_results(tmp_path, monkeypatch):
    source, old = _program([HOp, HOp])
    target, new = _program([])
    result = _result(source, target, _witness(source, target, old, new), tmp_path)
    monkeypatch.chdir(tmp_path)
    output = generate_docket(result)
    assert output.resolve() == tmp_path.resolve() / "docket.html"
    witness_only = output.read_text()
    assert "<h1>Docket</h1>" in witness_only
    assert "Witness only" in witness_only
    assert 'xlink:href="#rule-1"' in witness_only
    assert "Source pattern" in witness_only and "Target pattern" in witness_only
    assert "<strong>Verifier</strong>" not in witness_only

    report = verify(result, backends=())
    report_path = tmp_path / "report.json"
    report.save(report_path)
    annotated = generate_docket(result.artifact_path, report=report_path).read_text()
    assert "<strong>Verifier</strong> structural" in annotated
    assert "no configured rule backend supports identity encodings" in annotated
    assert "claim graph matches both kernels" in annotated
    assert '<strong>Step verdict</strong> <span class="status unsupported">UNSUPPORTED</span>' in annotated
    assert '<a href="#kernel-0"><span>@main</span><span class="rule-count muted">3/4 rules verified</span></a>' in annotated
    assert '<h3>Claim graph structure</h3><span class="status verified">VERIFIED</span>' in annotated

    # The IR hashes stay the same; the checked witness changes.
    artifact = json.loads(result.artifact_path.read_text())
    artifact["witness"]["claims"][1]["id"] = "another-site"
    result.artifact_path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError, match="different compilation artifact"):
        generate_docket(result.artifact_path, output, report=report)
    assert output.read_text() == annotated


@pytest.mark.skipif(shutil.which("dot") is None, reason="HTML graph export uses Graphviz")
def test_witness_report_matches_a_copied_step_to_a_report_without_fingerprint(tmp_path):
    source, old = _program([HOp, HOp])
    target, new = _program([])
    original = _result(source, target, _witness(source, target, old, new), tmp_path)
    copy = original.save(tmp_path / "copy.json")
    report = verify(original, backends=()).to_dict()
    del report["artifact_sha256"]
    del report["kernels"]
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))
    output = tmp_path / "witness.html"

    checked = generate_docket(copy, output, report=report_path).read_text()
    assert "Matched using the report’s recorded artifact" in checked
    assert "NOT RECORDED" in checked

    artifact = json.loads(copy.artifact_path.read_text())
    artifact["witness"]["claims"][1]["id"] = "another-site"
    copy.artifact_path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError, match="different compilation artifact"):
        generate_docket(copy.artifact_path, output, report=report_path)

    original.artifact_path.unlink()
    with pytest.raises(ValueError, match=r"Run verify\(\) on the saved compilation step"):
        generate_docket(copy.artifact_path, output, report=report_path)
