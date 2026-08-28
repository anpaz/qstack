from qstack.runtime import Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse


def test_kernel_evaluator_restarts_and_releases_measured_qubits() -> None:
    module = lower(parse('''QSTACKQASM 0.1; include "qstack/cliffords.inc"; qreg q[1]; creg c[1]; x q[0]; measure q[0] -> c[0];'''))
    machine = Machine(module, num_qubits=1)
    assert machine.single_shot() == [1]
    assert machine.single_shot() == [1]
