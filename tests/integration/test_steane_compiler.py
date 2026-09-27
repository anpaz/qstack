from qstack.dialect.core import CallOp, DecoderOp, KernelOp, SelectOp, SelectorOp
from qstack.passes.steane import lower_steane, steane_decode_bits
from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module

_PROGRAM = '''QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qreg q[1]; creg c[1]; x q[0]; measure q[0] -> c[0];
'''


def test_steane_generates_named_syndrome_kernels_and_executes() -> None:
    registry = CallbackRegistry()
    output = lower_steane(lower(parse(_PROGRAM)), registry)
    verify_module(output)
    assert any(isinstance(op, KernelOp) and "syndrome" in op.sym_name.data for op in output.body.ops)
    assert any(isinstance(op, CallOp) for op in output.walk())
    assert any(isinstance(op, SelectOp) for op in output.walk())
    syndrome_kernels = [
        op
        for op in output.body.ops
        if isinstance(op, KernelOp) and "syndrome" in op.sym_name.data
    ]
    assert {op.allocation_count for op in syndrome_kernels} == {3}
    assert Machine(num_qubits=10, registry=registry).single_shot(output) == [1]


def test_steane_decoder_corrects_one_bit_fault() -> None:
    assert steane_decode_bits((1, 0, 0, 0, 0, 0, 0)) == 0


def test_repeated_steane_uses_fresh_callback_sources() -> None:
    registry = CallbackRegistry()
    output = lower_steane(
        lower_steane(lower(parse(_PROGRAM)), registry), registry
    )
    verify_module(output)
    assert [op.sym_name.data for op in output.body.ops if isinstance(op, DecoderOp)] == [
        "steane.1:decode",
        "steane.2:decode",
    ]
    assert [op.sym_name.data for op in output.body.ops if isinstance(op, SelectorOp)] == [
        "steane.1:syndrome",
        "steane.2:syndrome",
    ]
    assert Machine(num_qubits=100, registry=registry).single_shot(output) == [1]
