r"""End-to-end test for the toy-ISA biased Bell program (Phase 4.1).

Mirrors ``mlir/examples/2.bell-biased.ipynb`` and the legacy
``examples/2.bell-biased.ipynb`` workflow: `skew(0.8)` followed by
`entangle` should yield a biased Bell state with $|11\rangle\approx 80\%$.
"""

from qstack_mlir.runtime import Machine
from qstack_mlir.surface.lowering import lower
from qstack_mlir.surface.parser import parse
from qstack_mlir.verifier import verify_module

_PROGRAM = """
QSTACKQASM 0.1;
include "qstack/toy.inc";

qreg q[2];
creg c[2];
skew(0.8) q[0];
entangle q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""


def test_bell_biased_module_verifies() -> None:
    module = lower(parse(_PROGRAM))
    verify_module(module)


def test_bell_biased_concentrates_on_one_one() -> None:
    module = lower(parse(_PROGRAM))
    machine = Machine(module, num_qubits=4)
    hist = dict(machine.shots("main", 4000).histogram())
    # Only the parallel Bell outcomes are reachable.
    assert set(hist.keys()) <= {(0, 0), (1, 1)}
    # bias=0.8 sends ~80% of the population to |11>.
    p11 = hist.get((1, 1), 0) / 4000
    assert 0.75 < p11 < 0.85, f"|11> fraction {p11} outside [0.75, 0.85]"
