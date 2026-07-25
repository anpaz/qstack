"""End-to-end pipelines ending in the neutral-atom dialect."""

from qstack.dialect.atoms import CzOp, RzOp, SxOp
from qstack.dialect.cliffords import CxOp, HOp, XOp
from qstack.passes.cliffords2atoms import compile_cliffords_to_atoms
from qstack.passes.toy2cliffords import compile_toy_to_cliffords
from qstack.runtime import Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module

_TOY_BELL = """
QSTACKQASM 0.1;
include "qstack/toy.inc";

qreg q[2];
creg c[2];
mix q[0];
entangle q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""


def _has_cliffords(module) -> bool:
    return any(isinstance(op, (HOp, XOp, CxOp)) for op in module.walk())


def test_toy_to_cliffords_to_atoms_executes_bell_program() -> None:
    module = lower(parse(_TOY_BELL))
    compile_toy_to_cliffords(module)
    compile_cliffords_to_atoms(module)
    verify_module(module)

    assert not _has_cliffords(module)
    assert any(isinstance(op, (RzOp, SxOp, CzOp)) for op in module.walk())

    histogram = dict(Machine(module, num_qubits=2).eval(shots=2000).histogram())
    assert set(histogram) <= {(0, 0), (1, 1)}
    for outcome in ((0, 0), (1, 1)):
        assert 800 < histogram.get(outcome, 0) < 1200

