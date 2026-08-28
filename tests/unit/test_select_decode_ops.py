from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.core import DecoderOp, KernelOp, MeasureOp, ReturnOp, SelectOp, SelectorOp
from qstack.verifier import verify_module


def test_declared_select_and_decode_interfaces_verify() -> None:
    case = Block(arg_types=[QubitType()]); case.add_op(ReturnOp(operands=[case.args[0]]))
    identity = KernelOp("id", input_types=[QubitType()], result_types=[QubitType()], allocates=0, region=Region([case]))
    main_body = Block(arg_types=[QubitType(), QubitType()]); bit = MeasureOp(operand=main_body.args[0]); main_body.add_op(bit)
    select = SelectOp(callee="choose", bit_operands=[bit.result], cases={"ok": SymbolRefAttr("id")}, case_arguments=[main_body.args[1]], result_types=[QubitType()]); main_body.add_op(select)
    out = MeasureOp(operand=select.results[0]); main_body.add_op(out); main_body.add_op(ReturnOp(operands=[out.result]))
    main = KernelOp("main", input_types=[], result_types=[BitType()], allocates=2, region=Region([main_body]))
    verify_module(ModuleOp([SelectorOp("choose", 1), DecoderOp("decode", 1), identity, main]))
