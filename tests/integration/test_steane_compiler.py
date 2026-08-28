from qstack.dialect.core import CallOp, DecoderOp, KernelOp, SelectOp, SelectorOp
from qstack.passes.steane import compile_steane, register_steane_callbacks, steane_decode_bits
from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module

_PROGRAM = '''QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qreg q[1]; creg c[1]; x q[0]; measure q[0] -> c[0];
'''


def test_steane_generates_named_syndrome_kernels_and_executes() -> None:
    output = compile_steane(lower(parse(_PROGRAM)))
    verify_module(output)
    assert any(isinstance(op, KernelOp) and "syndrome" in op.sym_name.data for op in output.body.ops)
    assert any(isinstance(op, CallOp) for op in output.walk())
    assert any(isinstance(op, SelectOp) for op in output.walk())
    registry = CallbackRegistry(); register_steane_callbacks(registry)
    assert Machine(output, num_qubits=10, registry=registry).single_shot() == [1]


def test_steane_decoder_corrects_one_bit_fault() -> None:
    assert steane_decode_bits((1, 0, 0, 0, 0, 0, 0)) == 0


def test_repeated_steane_reuses_canonical_callback_declarations() -> None:
    output = compile_steane(compile_steane(lower(parse(_PROGRAM))))
    verify_module(output)
    assert [op.sym_name.data for op in output.body.ops if isinstance(op, DecoderOp)] == [
        "__qstack_steane_decode"
    ]
    assert [op.sym_name.data for op in output.body.ops if isinstance(op, SelectorOp)] == [
        "__qstack_steane_syndrome"
    ]
    registry = CallbackRegistry(); register_steane_callbacks(registry)
    assert Machine(output, num_qubits=100, registry=registry).single_shot() == [1]
