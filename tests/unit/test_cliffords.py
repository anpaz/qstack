from qstack.dialect.cliffords import CxOp, HOp
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.validation import validate_module


def test_clifford_bell_kernel_verifies() -> None:
    module = lower(parse('''QSTACKQASM 0.1; include "qstack/cliffords.inc"; qubit[2] q; bit[2] c; h q[0]; cx q[0], q[1]; measure q[0] -> c[0]; measure q[1] -> c[1];'''))
    validate_module(module)
    assert any(isinstance(op, HOp) for op in module.walk())
    assert any(isinstance(op, CxOp) for op in module.walk())
