from qstack.passes.rep3_phase import lower_rep3_phase
from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.validation import validate_module

_PROGRAM = '''QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qubit[1] q; bit[1] c; x q[0]; measure q[0] -> c[0];
'''


def test_phase_rep3_is_kernel_only_and_executes() -> None:
    registry = CallbackRegistry()
    output = lower_rep3_phase(lower(parse(_PROGRAM)), registry)
    validate_module(output)
    assert Machine(num_qubits=3, registry=registry).single_shot(output) == [1]
