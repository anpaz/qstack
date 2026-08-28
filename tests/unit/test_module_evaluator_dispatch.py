from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import XOp
from qstack.dialect.core import CallOp, KernelOp, MeasureOp, ReturnOp, SelectOp, SelectorOp
from qstack.runtime import CallbackRegistry, Machine


def test_direct_kernel_call_dispatches() -> None:
    flip_body = Block(arg_types=[QubitType()]); x = XOp(flip_body.args[0]); flip_body.add_op(x); flip_body.add_op(ReturnOp(operands=[x.result]))
    flip = KernelOp("flip", input_types=[QubitType()], result_types=[QubitType()], allocates=0, region=Region([flip_body]))
    main_body = Block(arg_types=[QubitType()]); call = CallOp("flip", [main_body.args[0]], [QubitType()]); main_body.add_op(call)
    measure = MeasureOp(operand=call.results[0]); main_body.add_op(measure); main_body.add_op(ReturnOp(operands=[measure.result]))
    main = KernelOp("main", input_types=[], result_types=[BitType()], allocates=1, region=Region([main_body]))
    assert Machine(ModuleOp([flip, main]), num_qubits=1).single_shot() == [1]


def test_select_dispatches_case_kernel_directly() -> None:
    case_body = Block(arg_types=[QubitType()]); x = XOp(case_body.args[0]); case_body.add_op(x); case_body.add_op(ReturnOp(operands=[x.result]))
    flip = KernelOp("flip", input_types=[QubitType()], result_types=[QubitType()], allocates=0, region=Region([case_body]))
    main_body = Block(arg_types=[QubitType(), QubitType()]); bit = MeasureOp(operand=main_body.args[0]); main_body.add_op(bit)
    select = SelectOp(callee="pick", bit_operands=[bit.result], cases={"flip": SymbolRefAttr("flip")}, case_arguments=[main_body.args[1]], result_types=[QubitType()]); main_body.add_op(select)
    out = MeasureOp(operand=select.results[0]); main_body.add_op(out); main_body.add_op(ReturnOp(operands=[out.result]))
    main = KernelOp("main", input_types=[], result_types=[BitType()], allocates=2, region=Region([main_body]))
    registry = CallbackRegistry()
    @registry.selector("pick")
    def pick(bits): return "flip"
    assert Machine(ModuleOp([SelectorOp("pick", 1), flip, main]), num_qubits=2, registry=registry).single_shot() == [1]
