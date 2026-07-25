import logging

import pytest
from xdsl.dialects.builtin import FunctionType, ModuleOp, SymbolRefAttr, UnitAttr
from xdsl.dialects.func import FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Block, Region

from qstack_mlir.dialect import BitType, QubitType
from qstack_mlir.dialect.cliffords import XOp
from qstack_mlir.dialect.core import DecodeOp, KernelOp, MeasureOp, ReturnOp
from qstack_mlir.runtime import (
    CPU,
    QPU,
    Machine,
    Results,
    StateVectorQPU,
    StimQPU,
    UnregisteredCallback,
)
from qstack_mlir.runtime.analysis import StimCompatibilityError
from qstack_mlir.runtime.noise import NoiselessChannel
from qstack_mlir.runtime.qpu import GateApplication
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


def _x_module():
    return lower(
        parse(
            """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
x q[0];
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


def test_machine_auto_selects_stim_for_clifford_module() -> None:
    machine = Machine(_x_module(), num_qubits=1)

    assert isinstance(machine.qpu, StimQPU)
    assert machine.single_shot() == [1]


def test_machine_logs_selected_qpu(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="qstack"):
        Machine(_x_module(), num_qubits=1)
        Machine(_sx_squared_module(), num_qubits=1)

    assert "machine.qpu: selected StimQPU (requested=auto" in caplog.text
    assert "machine.qpu: selected StateVectorQPU (requested=auto" in caplog.text


def test_machine_auto_selects_statevector_for_non_clifford_module() -> None:
    machine = Machine(_sx_squared_module(), num_qubits=1)

    assert isinstance(machine.qpu, StateVectorQPU)
    assert machine.single_shot() == [1]


def test_machine_explicit_statevector_overrides_stim_compatible_module() -> None:
    machine = Machine(_x_module(), num_qubits=1, qpu="statevector")

    assert isinstance(machine.qpu, StateVectorQPU)
    assert machine.single_shot() == [1]


def test_machine_explicit_stim_rejects_non_clifford_module() -> None:
    with pytest.raises(StimCompatibilityError, match="atoms.sx"):
        Machine(_sx_squared_module(), num_qubits=1, qpu="stim")


def test_machine_explicit_stim_rejects_legacy_noise_argument() -> None:
    with pytest.raises(StimCompatibilityError, match="legacy NoiseChannel"):
        Machine(_x_module(), num_qubits=1, qpu="stim", noise=NoiselessChannel())


class _FakeQPU:
    def __init__(self) -> None:
        self.applied: list[str] = []
        self.restarted = False

    def restart(self) -> None:
        self.restarted = True

    def allocate(self) -> int:
        return 0

    def release(self, idx: int) -> None:
        pass

    def measure(self, idx: int) -> int:
        return 1

    def apply_gate(self, gate: GateApplication) -> None:
        self.applied.append(gate.op.name)


def test_machine_accepts_user_supplied_qpu() -> None:
    qpu = _FakeQPU()
    machine = Machine(_x_module(), num_qubits=1, qpu=qpu)

    assert machine.qpu is qpu
    assert machine.single_shot() == [1]
    assert qpu.restarted
    assert qpu.applied == ["cliffords.x"]


def test_machine_rejects_user_supplied_qpu_with_noise() -> None:
    with pytest.raises(ValueError, match="user-supplied qpu"):
        Machine(_x_module(), num_qubits=1, qpu=_FakeQPU(), noise=NoiselessChannel())
