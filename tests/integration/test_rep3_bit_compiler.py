from qstack.dialect.core import DecodeOp, DecoderOp, KernelOp, MeasureOp
from qstack.passes.rep3_bit import compile_rep3_bit, register_rep3_bit_callbacks
from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module

_PROGRAM = '''QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qreg q[1]; creg c[1]; x q[0]; measure q[0] -> c[0];
'''


def test_rep3_decodes_inside_named_main_kernel() -> None:
    output = compile_rep3_bit(lower(parse(_PROGRAM)))
    verify_module(output)
    main = next(op for op in output.body.ops if isinstance(op, KernelOp) and op.sym_name.data == "main")
    assert main.allocation_count == 3
    assert len([op for op in main.body.block.ops if isinstance(op, MeasureOp)]) == 3
    assert len([op for op in main.body.block.ops if isinstance(op, DecodeOp)]) == 1
    assert len([op for op in output.body.ops if isinstance(op, DecoderOp)]) == 1


def test_repeated_rep3_reuses_its_canonical_decoder() -> None:
    output = compile_rep3_bit(compile_rep3_bit(lower(parse(_PROGRAM))))
    assert [op.sym_name.data for op in output.body.ops if isinstance(op, DecoderOp)] == ["__qstack_rep3_bit_decode"]
    registry = CallbackRegistry(); register_rep3_bit_callbacks(registry)
    assert Machine(output, num_qubits=9, registry=registry).single_shot() == [1]
