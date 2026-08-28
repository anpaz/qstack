"""Kernel-only direct IR coverage for the DESIGN.md recursion example."""

from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, HOp
from qstack.dialect.core import KernelOp, MeasureOp, ReturnOp, SelectOp, SelectorOp
from qstack.verifier import verify_module


def _kernel(name, inputs, results, body, *, allocates=0):
    return KernelOp(name, input_types=inputs, result_types=results, allocates=allocates, region=Region([body]))


def _build_module() -> ModuleOp:
    identity_block = Block(arg_types=[QubitType()]); identity_block.add_op(ReturnOp(operands=[identity_block.args[0]]))
    identity = _kernel("id", [QubitType()], [QubitType()], identity_block)

    prepare_block = Block(arg_types=[QubitType(), QubitType()])
    h = HOp(prepare_block.args[0]); prepare_block.add_op(h)
    cx = CxOp(h.result, prepare_block.args[1]); prepare_block.add_op(cx)
    m = MeasureOp(operand=cx.target_out); prepare_block.add_op(m)
    select = SelectOp(callee="repeat_until_one", bit_operands=[m.result],
                      cases={"done": SymbolRefAttr("id"), "retry": SymbolRefAttr("prepare_one")},
                      case_arguments=[cx.control_out], result_types=[QubitType()])
    prepare_block.add_op(select); prepare_block.add_op(ReturnOp(operands=select.results))
    prepare = _kernel("prepare_one", [QubitType()], [QubitType()], prepare_block, allocates=1)

    main_block = Block(arg_types=[QubitType()])
    from qstack.dialect.core import CallOp
    call = CallOp("prepare_one", [main_block.args[0]], [QubitType()]); main_block.add_op(call)
    result = MeasureOp(operand=call.results[0]); main_block.add_op(result); main_block.add_op(ReturnOp(operands=[result.result]))
    main = KernelOp("main", input_types=[], result_types=[BitType()], allocates=1, region=Region([main_block]))
    return ModuleOp([SelectorOp("repeat_until_one", 1), identity, prepare, main])


def test_kernel_only_prepare_one_verifies() -> None:
    module = _build_module(); module.verify(); verify_module(module)


def test_kernel_only_prepare_one_has_no_legacy_control() -> None:
    module = _build_module()
    assert all(not op.name.startswith("func.") and op.name != "qstack.invoke" for op in module.walk())
