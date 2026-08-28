from qstack.dialect.cliffords import CxOp, HOp
from qstack.passes.cliffords2atoms import compile_cliffords_to_atoms
from qstack.surface.lowering import lower
from qstack.surface.parser import parse


def test_atoms_lowering_rewrites_kernel_gates() -> None:
    module = lower(parse('''QSTACKQASM 0.1; include "qstack/cliffords.inc"; qreg q[2]; creg c[2]; h q[0]; cx q[0], q[1]; measure q[0] -> c[0]; measure q[1] -> c[1];'''))
    compiled = compile_cliffords_to_atoms(module)
    assert not any(isinstance(op, (HOp, CxOp)) for op in compiled.walk())
    assert any(isinstance(op, (HOp, CxOp)) for op in module.walk())
