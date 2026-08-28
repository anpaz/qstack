import pytest

from qstack.runtime import Machine
from qstack.runtime.analysis import StimCompatibilityError
from qstack.surface.lowering import lower
from qstack.surface.parser import parse


def _module(include: str):
    return lower(parse(f'''QSTACKQASM 0.1; include "{include}"; qreg q[1]; creg c[1]; x q[0]; measure q[0] -> c[0];'''))


def test_machine_executes_main_only() -> None:
    machine = Machine(_module("qstack/cliffords.inc"), num_qubits=1)
    assert machine.single_shot() == [1]
    assert all(result == [1] for result in machine.eval(shots=5))


def test_machine_selects_stim_for_cliffords() -> None:
    assert Machine(_module("qstack/cliffords.inc"), num_qubits=1).qpu.__class__.__name__ == "StimQPU"


def test_machine_rejects_stim_for_non_clifford_module() -> None:
    non_clifford = lower(parse('''QSTACKQASM 0.1; include "qstack/atoms.inc"; qreg q[1]; creg c[1]; sx q[0]; measure q[0] -> c[0];'''))
    with pytest.raises(StimCompatibilityError):
        Machine(non_clifford, num_qubits=1, qpu="stim")
