from xdsl.dialects.builtin import ArrayAttr, StringAttr

from qstack.dialect.core import DecodeOp, DecoderOp, KernelOp, MeasureOp
from qstack.passes import PASS_HISTORY_ATTR
from qstack.passes.rep3_bit import lower_rep3_bit
from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module

_PROGRAM = '''QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qreg q[1]; creg c[1]; x q[0]; measure q[0] -> c[0];
'''


def test_rep3_decodes_inside_named_main_kernel() -> None:
    output = lower_rep3_bit(lower(parse(_PROGRAM)), CallbackRegistry())
    verify_module(output)
    main = next(op for op in output.body.ops if isinstance(op, KernelOp) and op.sym_name.data == "main")
    assert main.allocation_count == 3
    assert len([op for op in main.body.block.ops if isinstance(op, MeasureOp)]) == 3
    assert len([op for op in main.body.block.ops if isinstance(op, DecodeOp)]) == 1
    assert len([op for op in output.body.ops if isinstance(op, DecoderOp)]) == 1


def test_repeated_rep3_uses_fresh_callback_sources() -> None:
    registry = CallbackRegistry()
    output = lower_rep3_bit(
        lower_rep3_bit(lower(parse(_PROGRAM)), registry), registry
    )
    decoders = [op for op in output.body.ops if isinstance(op, DecoderOp)]
    assert [op.sym_name.data for op in decoders] == [
        "rep3_bit.1:decode",
        "rep3_bit.2:decode",
    ]
    assert output.attributes[PASS_HISTORY_ATTR] == ArrayAttr(
        [StringAttr("qstack.rep3-bit"), StringAttr("qstack.rep3-bit")]
    )
    assert Machine(num_qubits=9, registry=registry).single_shot(output) == [1]


def test_rep3_does_not_reuse_a_compatible_input_decoder() -> None:
    source = lower(parse(_PROGRAM))
    source.body.block.add_op(DecoderOp("existing_decoder", 3))
    output = lower_rep3_bit(source, CallbackRegistry())
    assert [op.sym_name.data for op in output.body.ops if isinstance(op, DecoderOp)] == [
        "existing_decoder",
        "rep3_bit.1:decode",
    ]


def test_rep3_uses_the_next_global_pass_index() -> None:
    source = lower(parse(_PROGRAM))
    source.attributes[PASS_HISTORY_ATTR] = ArrayAttr(
        [StringAttr("qstack.previous-pass")]
    )
    source.body.block.add_op(
        DecoderOp("rep3_bit.1:existing", 1)
    )
    output = lower_rep3_bit(source, CallbackRegistry())
    assert [op.sym_name.data for op in output.body.ops if isinstance(op, DecoderOp)] == [
        "rep3_bit.1:existing",
        "rep3_bit.2:decode",
    ]
    assert output.attributes[PASS_HISTORY_ATTR] == ArrayAttr(
        [StringAttr("qstack.previous-pass"), StringAttr("qstack.rep3-bit")]
    )
