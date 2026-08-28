from qstack.passes.rep3_phase import compile_rep3_phase, register_rep3_phase_callbacks
from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module

_PROGRAM = '''QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qreg q[1]; creg c[1]; x q[0]; measure q[0] -> c[0];
'''


def test_phase_rep3_is_kernel_only_and_executes() -> None:
    output = compile_rep3_phase(lower(parse(_PROGRAM)))
    verify_module(output)
    registry = CallbackRegistry(); register_rep3_phase_callbacks(registry)
    assert Machine(output, num_qubits=3, registry=registry).single_shot() == [1]
