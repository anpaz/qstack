from qstack.dialect.toy import EntangleOp, FlipOp, MixOp
from qstack.surface.lowering import lower
from qstack.surface.parser import parse


def test_toy_ops_lower_inside_main_kernel() -> None:
    module = lower(parse('''QSTACKQASM 0.1; include "qstack/toy.inc"; qreg q[2]; creg c[2]; flip q[0]; mix q[1]; entangle q[0], q[1]; measure q[0] -> c[0]; measure q[1] -> c[1];'''))
    assert {type(op) for op in module.walk()} >= {FlipOp, MixOp, EntangleOp}
