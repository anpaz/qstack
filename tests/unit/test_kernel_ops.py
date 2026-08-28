from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.core import KernelOp, MeasureOp, ReturnOp
from qstack.verifier import verify_module


def test_named_kernel_declares_allocations_and_returns_bits() -> None:
    body = Block(arg_types=[QubitType()]); measurement = MeasureOp(operand=body.args[0]); body.add_op(measurement); body.add_op(ReturnOp(operands=[measurement.result]))
    module = ModuleOp([KernelOp("main", input_types=[], result_types=[BitType()], allocates=1, region=Region([body]))])
    module.verify(); verify_module(module)
