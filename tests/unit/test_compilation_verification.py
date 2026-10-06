"""A tiny witnessed compiler exercises the API without instrumenting existing passes."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from xdsl.dialects.builtin import ModuleOp
from xdsl.dialects.builtin import StringAttr
from xdsl.ir import Block, Region

from qstack.compilation import CompilationResult
from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import HOp, XOp
from qstack.dialect.core import DecodeOp, DecoderOp, KernelOp, MeasureOp, ReturnOp
from qstack.dialect.h2 import U1Op
from qstack.passes.clifford_peephole import CliffordPeepholeOptimization
from qstack.passes.cliffords2h2 import CliffordsToH2Lowering
from qstack.surface import compile_qasm
from qstack.verification import (
    Circuit,
    Edge,
    Gate,
    KernelBoundary,
    Node,
    Rule,
    ValueRef,
    Witness,
    installed_rule_backends,
    verify,
)
from qstack.verification.plugins import ExternalRuleBackend
import qstack.verification.plugins as rule_backends


def _matrix_backend():
    for backend in installed_rule_backends():
        if backend.name == "matrix":
            return backend
    pytest.skip("install the independent quivalence distribution")


def test_external_rule_backend_receives_serialized_rule() -> None:
    received = []

    def check(payload):
        received.append(payload)
        return {"rule": payload["id"], "status": "VERIFIED", "detail": "checked"}

    backend = ExternalRuleBackend(SimpleNamespace(name="stub", load=lambda: check))
    rule = Rule("empty", Circuit(0, ()), Circuit(0, ()))
    assert backend.check(rule).status == "VERIFIED"
    assert received == [{"id": "empty", "source": {"width": 0, "gates": []}, "target": {"width": 0, "gates": []}}]
    json.dumps(received[0])


def test_external_rule_backend_rejects_bad_verdict() -> None:
    backend = ExternalRuleBackend(
        SimpleNamespace(name="stub", load=lambda: lambda _: {"rule": "wrong", "status": "VERIFIED", "detail": "checked"})
    )
    assert backend.check(Rule("expected", Circuit(0, ()), Circuit(0, ()))).status == "UNSUPPORTED"


def test_rule_backend_discovery_allows_no_external_install(monkeypatch) -> None:
    monkeypatch.setattr(rule_backends, "entry_points", lambda **_: ())
    assert installed_rule_backends() == ()


def _program(gates):
    block = Block(arg_types=[QubitType()])
    wire = block.args[0]
    instances = []
    for constructor in gates:
        gate = constructor(wire)
        block.add_op(gate)
        instances.append(gate)
        wire = gate.results[0]
    measure = MeasureOp(operand=wire)
    block.add_op(measure)
    block.add_op(ReturnOp(operands=[measure.result]))
    module = ModuleOp([
        KernelOp(
            "main", input_types=[], result_types=[BitType()], allocates=1,
            region=Region([block]),
        )
    ])
    return module, instances


def _witness(source, target, old_gates, new_gates):
    source_measure = len(old_gates)
    target_measure = len(new_gates)
    first_source = ValueRef("arg", 0)
    last_source = ValueRef("result", source_measure - 1) if old_gates else first_source
    first_target = ValueRef("arg", 0)
    last_target = ValueRef("result", target_measure - 1) if new_gates else first_target
    edges = (
        Edge("input", "main", (first_source,), (first_target,)),
        Edge("after_rule", "main", (last_source,), (last_target,)),
        Edge("bit", "main", (ValueRef("result", source_measure),), (ValueRef("result", target_measure),)),
    )
    rule = Rule(
        "rewrite",
        Circuit(1, tuple(Gate.from_op(op, (0,)) for op in old_gates)),
        Circuit(1, tuple(Gate.from_op(op, (0,)) for op in new_gates)),
    )
    nodes = (
        Node("allocation", "main", "allocation", (), (), (), ("input",)),
        Node("site", "main", "rule", tuple(range(source_measure)), tuple(range(target_measure)), ("input",), ("after_rule",), "rewrite"),
        Node("measure", "main", "identity", (source_measure,), (target_measure,), ("after_rule",), ("bit",)),
        Node("return", "main", "identity", (source_measure + 1,), (target_measure + 1,), ("bit",), ()),
    )
    return Witness.bind(
        source, target, rules=(rule,), nodes=nodes, edges=edges,
        kernels=(KernelBoundary("main", ()),),
    )


def test_compilation_result_has_only_latest_step(tmp_path) -> None:
    source = compile_qasm('QSTACKQASM 0.1; include "qstack/cliffords.inc"; qreg q[1]; creg c[1]; h q[0]; measure q[0] -> c[0];')
    assert source.witness is None
    target, _ = _program([])
    first = CompilationResult.from_step(source, target, artifact_path=tmp_path / "first.json")
    assert first.witness is None
    assert verify(first).status == "UNSUPPORTED"
    second = CompilationResult.from_step(first, source.module.clone(), artifact_path=tmp_path / "second.json")
    data = json.loads(second.artifact_path.read_text())
    assert data["source"] != data["target"]
    assert data["witness"] is None
    assert CompilationResult.load(second.artifact_path).artifact_path == second.artifact_path
    existing_pass_result = CliffordsToH2Lowering().run(source)
    assert existing_pass_result.witness is not None
    assert existing_pass_result.artifact_path is not None


def test_matrix_verifies_cancellation_and_saved_artifact(tmp_path) -> None:
    source_module, old_gates = _program([HOp, HOp])
    target_module, new_gates = _program([])
    witness = _witness(source_module, target_module, old_gates, new_gates)
    source = CompilationResult.from_module(source_module)
    result = CompilationResult.from_step(source, target_module, witness, artifact_path=tmp_path / "cancel.json")
    report = verify(result, backends=(_matrix_backend(),))
    assert report.status == "VERIFIED"
    assert report.rules[0].sites == ("site",)
    assert verify(CompilationResult.load(result.artifact_path), backends=(_matrix_backend(),)).status == "VERIFIED"
    report.save(tmp_path / "report.json")
    assert json.loads((tmp_path / "report.json").read_text())["status"] == "VERIFIED"


def test_pass_run_builds_witness_from_replacements() -> None:
    source_module, _ = _program([HOp, HOp])
    result = CliffordPeepholeOptimization().run(CompilationResult.from_module(source_module))
    assert result.witness is not None
    assert verify(result, backends=(_matrix_backend(),)).status == "VERIFIED"
    repeated, _ = _program([HOp, HOp, HOp, HOp])
    repeated_result = CliffordPeepholeOptimization().run(CompilationResult.from_module(repeated))
    assert len(repeated_result.witness.rules) == 1
    assert len(verify(repeated_result, backends=(_matrix_backend(),)).rules[0].sites) == 2


def test_frontend_peephole_witness_round_trips_and_verifies(tmp_path) -> None:
    _matrix_backend()
    source = compile_qasm(
        'QSTACKQASM 0.1; include "qstack/cliffords.inc"; '
        'qreg q[1]; creg c[1]; h q[0]; h q[0]; '
        's q[0]; s q[0]; measure q[0] -> c[0];'
    )
    result = CliffordPeepholeOptimization().run(source).save(tmp_path / "peephole.json")
    assert result.witness is not None
    assert len(result.witness.rules) == 2
    reloaded = CompilationResult.load(result.artifact_path)
    report = verify(reloaded)
    assert report.status == "VERIFIED"
    assert {rule.backend for rule in report.rules} == {"matrix"}


def test_repeated_sites_check_one_rule_once(tmp_path) -> None:
    source_module, gates = _program([HOp, HOp, HOp, HOp])
    target_module, _ = _program([])
    target_input = ValueRef("arg", 0)
    edges = (
        Edge("entry", "main", (ValueRef("arg", 0),), (target_input,)),
        Edge("middle", "main", (ValueRef("result", 1),), (target_input,)),
        Edge("end", "main", (ValueRef("result", 3),), (target_input,)),
        Edge("bit", "main", (ValueRef("result", 4),), (ValueRef("result", 0),)),
    )
    rule = Rule("cancel", Circuit(1, (Gate.from_op(gates[0], (0,)), Gate.from_op(gates[1], (0,)))), Circuit(1, ()))
    nodes = (
        Node("allocation", "main", "allocation", (), (), (), ("entry",)),
        Node("first", "main", "rule", (0, 1), (), ("entry",), ("middle",), "cancel"),
        Node("second", "main", "rule", (2, 3), (), ("middle",), ("end",), "cancel"),
        Node("measure", "main", "identity", (4,), (0,), ("end",), ("bit",)),
        Node("return", "main", "identity", (5,), (1,), ("bit",), ()),
    )
    witness = Witness.bind(
        source_module, target_module, rules=(rule,), nodes=nodes, edges=edges,
        kernels=(KernelBoundary("main", ()),),
    )
    result = CompilationResult.from_step(
        CompilationResult.from_module(source_module), target_module, witness,
        artifact_path=tmp_path / "repeated.json",
    )
    report = verify(result, backends=(_matrix_backend(),))
    assert report.status == "VERIFIED"
    assert len(report.rules) == 1
    assert report.rules[0].sites == ("first", "second")


def test_matrix_refutes_missing_phase(tmp_path) -> None:
    source_module, old_gates = _program([XOp])
    target_module, new_gates = _program([lambda wire: U1Op(wire, math.pi, 0)])
    witness = _witness(source_module, target_module, old_gates, new_gates)
    result = CompilationResult.from_step(
        CompilationResult.from_module(source_module), target_module, witness,
        artifact_path=tmp_path / "phase.json",
    )
    report = verify(result, backends=(_matrix_backend(),))
    assert report.status == "REFUTED"
    assert "matrix entry" in report.rules[0].detail


def test_witness_builder_exposes_existing_h2_phase_mismatch() -> None:
    source_module, _ = _program([XOp])
    result = CliffordsToH2Lowering().run(CompilationResult.from_module(source_module))
    report = verify(result, backends=(_matrix_backend(),))
    assert report.status == "REFUTED"
    assert report.rules[0].sites


def test_tampered_artifact_is_rejected_before_rule_checks(tmp_path) -> None:
    source_module, old_gates = _program([HOp, HOp])
    target_module, new_gates = _program([])
    witness = _witness(source_module, target_module, old_gates, new_gates)
    result = CompilationResult.from_step(
        CompilationResult.from_module(source_module), target_module, witness,
        artifact_path=tmp_path / "step.json",
    )
    payload = json.loads(result.artifact_path.read_text())
    payload["source"] += "\n"
    result.artifact_path.write_text(json.dumps(payload))
    report = verify(result)
    assert report.status == "REFUTED"
    assert "SHA-256" in report.detail


def test_mutated_returned_module_does_not_match_its_artifact(tmp_path) -> None:
    source_module, old_gates = _program([HOp, HOp])
    target_module, new_gates = _program([])
    witness = _witness(source_module, target_module, old_gates, new_gates)
    result = CompilationResult.from_step(
        CompilationResult.from_module(source_module), target_module, witness,
        artifact_path=tmp_path / "step.json",
    )
    result.module.attributes["tampered"] = StringAttr("yes")
    assert "result module differs" in verify(result).detail


def test_wrong_claim_binding_is_refuted(tmp_path) -> None:
    source_module, old_gates = _program([HOp, HOp])
    target_module, new_gates = _program([])
    valid = _witness(source_module, target_module, old_gates, new_gates)
    nodes = tuple(
        Node(node.id, node.kernel, node.kind, node.source_ops, node.target_ops,
             ("bit",) if node.id == "site" else node.inputs, node.outputs, node.rule)
        for node in valid.nodes
    )
    wrong = Witness.bind(
        source_module, target_module, rules=valid.rules, nodes=nodes,
        edges=valid.edges, kernels=valid.kernels,
    )
    result = CompilationResult.from_step(
        CompilationResult.from_module(source_module), target_module, wrong,
        artifact_path=tmp_path / "wrong.json",
    )
    assert verify(result).status == "REFUTED"


def test_callback_host_wire_order_is_checked(tmp_path) -> None:
    def module(reverse: bool):
        block = Block(arg_types=[QubitType(), QubitType()])
        first_measure = MeasureOp(operand=block.args[0])
        second_measure = MeasureOp(operand=block.args[1])
        first_decode = DecodeOp(callee="a", bit_operands=[first_measure.result])
        second_decode = DecodeOp(callee="b", bit_operands=[second_measure.result])
        block.add_ops([first_measure, second_measure])
        block.add_ops([second_decode, first_decode] if reverse else [first_decode, second_decode])
        block.add_op(ReturnOp(operands=[first_decode.result, second_decode.result]))
        return ModuleOp([
            DecoderOp("a", 1), DecoderOp("b", 1),
            KernelOp("main", input_types=[], result_types=[BitType(), BitType()],
                     allocates=2, region=Region([block])),
        ])

    source_module, target_module = module(False), module(True)
    edges = (
        Edge("q0", "main", (ValueRef("arg", 0),), (ValueRef("arg", 0),)),
        Edge("q1", "main", (ValueRef("arg", 1),), (ValueRef("arg", 1),)),
        Edge("m0", "main", (ValueRef("result", 0),), (ValueRef("result", 0),)),
        Edge("m1", "main", (ValueRef("result", 1),), (ValueRef("result", 1),)),
        Edge("d0", "main", (ValueRef("result", 2),), (ValueRef("result", 3),)),
        Edge("d1", "main", (ValueRef("result", 3),), (ValueRef("result", 2),)),
    )
    nodes = (
        Node("alloc0", "main", "allocation", (), (), (), ("q0",)),
        Node("alloc1", "main", "allocation", (), (), (), ("q1",)),
        Node("measure0", "main", "identity", (0,), (0,), ("q0",), ("m0",)),
        Node("measure1", "main", "identity", (1,), (1,), ("q1",), ("m1",)),
        Node("decode0", "main", "identity", (2,), (3,), ("m0",), ("d0",)),
        Node("decode1", "main", "identity", (3,), (2,), ("m1",), ("d1",)),
        Node("return", "main", "identity", (4,), (4,), ("d0", "d1"), ()),
    )
    witness = Witness.bind(
        source_module, target_module, rules=(), nodes=nodes, edges=edges,
        kernels=(KernelBoundary("main", ()),),
    )
    result = CompilationResult.from_step(
        CompilationResult.from_module(source_module), target_module, witness,
        artifact_path=tmp_path / "callbacks.json",
    )
    report = verify(result)
    assert report.status == "REFUTED"
    assert "host-wire order" in report.detail
