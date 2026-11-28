from dataclasses import replace

from qstack.compilation import CompilationResult
from qstack.dialect.core import AllocOp, CallOp, DecoderOp, KernelOp, SelectOp, SelectorOp
from qstack.passes.steane import lower_steane, steane_decode_bits
from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.validation import validate_module
from qstack.verification import verify

_PROGRAM = '''QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qubit[1] q; bit[1] c; x q[0]; measure q[0] -> c[0];
'''


def test_steane_generates_named_syndrome_kernels_and_executes() -> None:
    registry = CallbackRegistry()
    output = lower_steane(lower(parse(_PROGRAM)), registry)
    validate_module(output)
    assert any(isinstance(op, KernelOp) and "syndrome" in op.sym_name.data for op in output.body.ops)
    assert any(isinstance(op, CallOp) for op in output.walk())
    assert any(isinstance(op, SelectOp) for op in output.walk())
    syndrome_kernels = [
        op
        for op in output.body.ops
        if isinstance(op, KernelOp) and "syndrome" in op.sym_name.data
    ]
    assert {sum(isinstance(inner, AllocOp) for inner in op.body.block.ops) for op in syndrome_kernels} == {3}
    assert Machine(num_qubits=10, registry=registry).single_shot(output) == [1]


def test_steane_reports_unsupported_rewrites_and_introduced_kernels(tmp_path) -> None:
    source = CompilationResult.from_module(lower(parse(_PROGRAM)))
    result = lower_steane(source, CallbackRegistry()).save(tmp_path / "steane.json")
    loaded = CompilationResult.load(result.artifact_path)
    assert loaded.witness == result.witness
    witness = loaded.witness
    assert witness is not None
    assert len(witness.introduced_kernels) == 17
    assert {claim.kernel for claim in witness.claims} == {"main"}

    correction, = (rule for rule in witness.rules if rule.kind == "unsupported")
    assert [op.name for op in correction.source.operations] == ["cliffords.x"]
    assert any(op.name == "qstack.select" for op in correction.target.operations)

    report = verify(loaded, backends=())
    assert report.status == "UNSUPPORTED"
    verdicts = {rule.rule: rule.status for rule in report.rules}
    assert verdicts[correction.id] == "UNSUPPORTED"
    assert {entry.kernel: entry.status for entry in report.kernels} == {
        "main": "VERIFIED",
        **dict.fromkeys(witness.introduced_kernels, "UNSUPPORTED"),
    }

    incomplete = replace(witness, introduced_kernels=witness.introduced_kernels[:-1])
    forged = CompilationResult.from_step(source, loaded.module, incomplete)
    report = verify(forged, backends=())
    assert report.status == "REFUTED"
    assert "introduced kernels do not match the target" in report.detail


def test_steane_decoder_corrects_one_bit_fault() -> None:
    assert steane_decode_bits((1, 0, 0, 0, 0, 0, 0)) == 0


def test_repeated_steane_uses_fresh_callback_sources() -> None:
    registry = CallbackRegistry()
    output = lower_steane(
        lower_steane(lower(parse(_PROGRAM)), registry), registry
    )
    validate_module(output)
    assert [op.sym_name.data for op in output.body.ops if isinstance(op, DecoderOp)] == [
        "steane.1:decode",
        "steane.2:decode",
    ]
    assert [op.sym_name.data for op in output.body.ops if isinstance(op, SelectorOp)] == [
        "steane.1:syndrome",
        "steane.2:syndrome",
    ]
    assert Machine(num_qubits=100, registry=registry).single_shot(output) == [1]
