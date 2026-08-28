import pytest
from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, HOp
from qstack.dialect.core import CallOp, KernelOp, MeasureOp, ReturnOp
from qstack.verifier import LinearityError, verify_module


def _kernel(name, inputs, results, body, *, allocates=0):
    return KernelOp(name, input_types=inputs, result_types=results, allocates=allocates, region=Region([body]))


def test_verifier_rejects_modules_without_main() -> None:
    block = Block(arg_types=[]); block.add_op(ReturnOp(operands=[]))
    with pytest.raises(LinearityError, match="@main"):
        verify_module(ModuleOp([KernelOp("other", input_types=[], result_types=[], allocates=0, region=Region([block]))]))


def test_verifier_rejects_main_returning_a_qubit() -> None:
    block = Block(arg_types=[QubitType()]); block.add_op(ReturnOp(operands=[block.args[0]]))
    with pytest.raises(LinearityError, match="cannot return a qubit"):
        verify_module(ModuleOp([KernelOp("main", input_types=[], result_types=[QubitType()], allocates=1, region=Region([block]))]))


def test_verifier_rejects_wrong_entry_signature() -> None:
    block = Block(arg_types=[]); block.add_op(ReturnOp(operands=[]))
    with pytest.raises(LinearityError, match="entry arguments"):
        verify_module(ModuleOp([KernelOp("main", input_types=[], result_types=[], allocates=1, region=Region([block]))]))


def test_verifier_accepts_a_fresh_qubit_escaping_by_teleportation() -> None:
    """A borrowed qubit may die inside the kernel while a fresh one is returned."""

    body = Block(arg_types=[QubitType(), QubitType(), QubitType()])
    psi, a, b = body.args
    h_a = HOp(a); body.add_op(h_a)
    bell = CxOp(h_a.result, b); body.add_op(bell)
    entangle = CxOp(psi, bell.control_out); body.add_op(entangle)
    basis = HOp(entangle.control_out); body.add_op(basis)
    m0 = MeasureOp(operand=basis.result); body.add_op(m0)
    m1 = MeasureOp(operand=entangle.target_out); body.add_op(m1)
    body.add_op(ReturnOp(operands=[bell.target_out, m0.result, m1.result]))
    teleport = _kernel("teleport", [QubitType()], [QubitType(), BitType(), BitType()], body, allocates=2)

    main_block = Block(arg_types=[QubitType()])
    call = CallOp("teleport", [main_block.args[0]], [QubitType(), BitType(), BitType()])
    main_block.add_op(call)
    final = MeasureOp(operand=call.results[0]); main_block.add_op(final)
    main_block.add_op(ReturnOp(operands=[final.result, call.results[1], call.results[2]]))
    main = _kernel("main", [], [BitType(), BitType(), BitType()], main_block, allocates=1)

    verify_module(ModuleOp([teleport, main]))


def test_verifier_accepts_a_kernel_returning_more_qubits_than_it_borrows() -> None:
    """A state preparation borrows nothing and hands its fresh qubit to the caller."""

    prep_block = Block(arg_types=[QubitType()])
    h = HOp(prep_block.args[0]); prep_block.add_op(h)
    prep_block.add_op(ReturnOp(operands=[h.result]))
    prepare = _kernel("prepare_plus", [], [QubitType()], prep_block, allocates=1)

    main_block = Block(arg_types=[])
    call = CallOp("prepare_plus", [], [QubitType()]); main_block.add_op(call)
    measure = MeasureOp(operand=call.results[0]); main_block.add_op(measure)
    main_block.add_op(ReturnOp(operands=[measure.result]))
    main = _kernel("main", [], [BitType()], main_block)

    verify_module(ModuleOp([prepare, main]))
