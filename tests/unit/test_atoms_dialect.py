from qstack.dialect.atoms import RzOp, SxOp
from qstack.surface.lowering import lower
from qstack.surface.parser import parse


def test_atoms_surface_kernel_uses_declared_gate_ops() -> None:
    module = lower(parse('''QSTACKQASM 0.1; include "qstack/atoms.inc"; qreg q[1]; creg c[1]; rz(0.5) q[0]; sx q[0]; measure q[0] -> c[0];'''))
    assert any(isinstance(op, RzOp) for op in module.walk())
    assert any(isinstance(op, SxOp) for op in module.walk())
