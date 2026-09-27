from qstack.passes.rep3_phase import lower_rep3_phase
from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module

_PROGRAM = '''QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qreg q[1]; creg c[1]; x q[0]; measure q[0] -> c[0];
'''


def test_phase_rep3_is_kernel_only_and_executes() -> None:
    registry = CallbackRegistry()
    output = lower_rep3_phase(lower(parse(_PROGRAM)), registry)
    verify_module(output)
    assert Machine(num_qubits=3, registry=registry).single_shot(output) == [1]
