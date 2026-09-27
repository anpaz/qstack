import pytest

from qstack.runtime import Machine
from qstack.runtime.analysis import StimCompatibilityError
from qstack.surface.lowering import lower
from qstack.surface.parser import parse


def _module(include: str):
    return lower(parse(f'''QSTACKQASM 0.1; include "{include}"; qreg q[1]; creg c[1]; x q[0]; measure q[0] -> c[0];'''))


def test_machine_executes_main_only() -> None:
    module = _module("qstack/cliffords.inc")
    machine = Machine(num_qubits=1)
    assert machine.single_shot(module) == [1]
    assert all(result == [1] for result in machine.eval(module, shots=5))


def test_machine_can_evaluate_multiple_programs() -> None:
    one = _module("qstack/cliffords.inc")
    zero = lower(parse('''QSTACKQASM 0.1; include "qstack/cliffords.inc"; qreg q[1]; creg c[1]; measure q[0] -> c[0];'''))
    machine = Machine(num_qubits=1)

    assert machine.single_shot(one) == [1]
    assert machine.single_shot(zero) == [0]
    assert machine.single_shot(one) == [1]


def test_machine_without_fixed_qpu_selects_per_evaluation() -> None:
    clifford = _module("qstack/cliffords.inc")
    non_clifford = lower(parse('''QSTACKQASM 0.1; include "qstack/atoms.inc"; qreg q[1]; creg c[1]; sx q[0]; measure q[0] -> c[0];'''))
    machine = Machine(num_qubits=1)

    machine.single_shot(clifford)
    machine.single_shot(non_clifford)

    assert set(machine._qpus) == {"stim", "statevector"}


def test_machine_rejects_stim_for_non_clifford_module() -> None:
    non_clifford = lower(parse('''QSTACKQASM 0.1; include "qstack/atoms.inc"; qreg q[1]; creg c[1]; sx q[0]; measure q[0] -> c[0];'''))
    machine = Machine(num_qubits=1, qpu="stim")
    with pytest.raises(StimCompatibilityError):
        machine.single_shot(non_clifford)
