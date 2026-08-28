import pytest

from qstack.dialect.atoms import RzOp as AtomsRzOp
from qstack.dialect.h2 import RzOp as H2RzOp
from qstack.surface.lowering import lower
from qstack.surface.parser import parse


def test_includes_select_the_target_isa_for_kernel_bodies() -> None:
    h2 = lower(parse('''QSTACKQASM 0.1; include "qstack/h2.inc"; qreg q[1]; creg c[1]; rz(0.5) q[0]; measure q[0] -> c[0];'''))
    atoms = lower(parse('''QSTACKQASM 0.1; include "qstack/atoms.inc"; qreg q[1]; creg c[1]; rz(0.5) q[0]; measure q[0] -> c[0];'''))
    assert any(isinstance(op, H2RzOp) for op in h2.walk())
    assert any(isinstance(op, AtomsRzOp) for op in atoms.walk())


def test_unknown_gate_is_rejected() -> None:
    with pytest.raises(NotImplementedError):
        lower(parse('''QSTACKQASM 0.1; include "qstack/h2.inc"; qreg q[1]; creg c[1]; h q[0]; measure q[0] -> c[0];'''))
