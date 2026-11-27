from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.core import AllocOp, KernelOp, MeasureOp, ReturnOp
from qstack.validation import validate_module


def test_named_kernel_declares_allocations_and_returns_bits() -> None:
    body = Block(); qubit = AllocOp(); body.add_op(qubit)
    measurement = MeasureOp(operand=qubit.result); body.add_op(measurement); body.add_op(ReturnOp(operands=[measurement.result]))
    module = ModuleOp([KernelOp("main", input_types=[], result_types=[BitType()], region=Region([body]))])
    validate_module(module)
