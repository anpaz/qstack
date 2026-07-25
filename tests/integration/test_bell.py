"""End-to-end test for the Bell-state example notebook.

Mirrors ``mlir/examples/0.bell.ipynb``: parses a tiny QASM program that
prepares $\\tfrac{1}{\\sqrt{2}}(|00\\rangle+|11\\rangle)$ using Cliffords,
lowers it, runs 4000 shots, and asserts the histogram is concentrated on
``(0, 0)`` and ``(1, 1)`` in roughly equal proportions.
"""

from qstack_mlir.runtime import CallbackRegistry, Machine
from qstack_mlir.surface.lowering import lower
from qstack_mlir.surface.parser import parse
from qstack_mlir.verifier import verify_module

BELL_PROGRAM = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[2];
creg c[2];
h q[0];
cx q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""


def test_bell_module_verifies() -> None:
    module = lower(parse(BELL_PROGRAM))
    verify_module(module)


def test_bell_statistics() -> None:
    module = lower(parse(BELL_PROGRAM))
    machine = Machine(module, num_qubits=4, registry=CallbackRegistry())
    results = machine.eval(shots=4000)
    hist = dict(results.histogram())

    # Only the two Bell outcomes should appear.
    assert set(hist.keys()) == {(0, 0), (1, 1)}, f"unexpected outcomes in Bell histogram: {hist!r}"
    # Each outcome should be ~50%; allow a wide statistical band.
    for key in [(0, 0), (1, 1)]:
        assert 1600 < hist[key] < 2400, f"Bell outcome {key} count {hist[key]} outside [1600, 2400]"
