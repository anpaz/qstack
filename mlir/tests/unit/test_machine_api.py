import pytest
from xdsl.dialects.builtin import FunctionType, ModuleOp, SymbolRefAttr, UnitAttr
from xdsl.dialects.func import FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Block, Region

from qstack_mlir.dialect import BitType, QubitType
from qstack_mlir.dialect.cliffords import XOp
from qstack_mlir.dialect.core import DecodeOp, KernelOp, MeasureOp, ReturnOp
from qstack_mlir.runtime import CPU, QPU, Machine, Results, UnregisteredCallback
from qstack_mlir.surface.lowering import lower
from qstack_mlir.surface.parser import parse


def _sx_squared_module():
    return lower(
        parse(
            """
QSTACKQASM 0.1;
include "qstack/atoms.inc";

qreg q[1];
creg c[1];
sx q[0];
sx q[0];
measure q[0] -> c[0];
"""
        )
    )


def test_machine_single_shot_runs_main_by_default() -> None:
    machine = Machine(_sx_squared_module(), num_qubits=1)

    assert isinstance(machine.qpu, QPU)
    assert isinstance(machine.cpu, CPU)
    assert machine.single_shot() == [1]


def test_machine_eval_matches_legacy_shape() -> None:
    machine = Machine(_sx_squared_module(), num_qubits=1)

    results = machine.eval(shots=5)

    assert isinstance(results, Results)
    assert results.shots == 5
    assert all(result == [1] for result in results)


def test_machine_eval_accepts_explicit_shot_count() -> None:
    machine = Machine(_sx_squared_module(), num_qubits=1)

    results = machine.eval(shots=3)

    assert results.shots == 3
    assert all(result == [1] for result in results)


def test_machine_defaults_to_empty_callback_registry() -> None:
    decl = FuncOp.external("missing_decoder", [BitType()], [BitType()])
    decl.attributes["qstack.decoder"] = UnitAttr()

    outer = Block(arg_types=[])
    kbody = Block(arg_types=[QubitType()])
    x = XOp(kbody.args[0])
    kbody.add_op(x)
    meas = MeasureOp(operand=x.result)
    kbody.add_op(meas)
    kbody.add_op(ReturnOp(operands=[meas.result]))
    kernel = KernelOp(result_types=[BitType()], region=Region([kbody]))
    outer.add_op(kernel)
    decode = DecodeOp(callee=SymbolRefAttr("missing_decoder"), bit_operands=[kernel.results[0]])
    outer.add_op(decode)
    outer.add_op(FuncReturn.create(operands=[decode.result]))
    main = FuncOp("main", FunctionType.from_lists([], [BitType()]), Region([outer]))
    machine = Machine(ModuleOp([decl, main]), num_qubits=1)

    with pytest.raises(UnregisteredCallback, match="missing_decoder"):
        machine.single_shot()
