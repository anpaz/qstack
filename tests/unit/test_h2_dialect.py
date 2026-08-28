from qstack.dialect.h2 import RzOp, U1Op
from qstack.surface.lowering import lower
from qstack.surface.parser import parse


def test_h2_surface_kernel_uses_declared_gate_ops() -> None:
    module = lower(parse('''QSTACKQASM 0.1; include "qstack/h2.inc"; qreg q[1]; creg c[1]; u1(0.1, 0.2) q[0]; rz(0.3) q[0]; measure q[0] -> c[0];'''))
    assert any(isinstance(op, U1Op) for op in module.walk())
    assert any(isinstance(op, RzOp) for op in module.walk())
