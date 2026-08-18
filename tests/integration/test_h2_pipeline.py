"""End-to-end parity pipelines ending in the H2-native dialect."""

from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, YOp, ZOp
from qstack.dialect.h2 import RzOp, U1Op, ZzOp
from qstack.passes.cliffords2h2 import compile_cliffords_to_h2
from qstack.passes.rep3_bit import compile_rep3_bit, register_rep3_bit_callbacks
from qstack.passes.rep3_phase import compile_rep3_phase, register_rep3_phase_callbacks
from qstack.passes.toy2cliffords import compile_toy_to_cliffords
from qstack.runtime import CallbackRegistry, Machine
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

_FLIP = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
x q[0];
measure q[0] -> c[0];
"""


def _has_cliffords(module) -> bool:
    return any(isinstance(op, (CxOp, CzOp, HOp, SOp, XOp, YOp, ZOp)) for op in module.walk())


def test_toy_to_cliffords_to_h2_executes_bell_program() -> None:
    module = lower(parse(_TOY_BELL))
    compile_toy_to_cliffords(module)
    compile_cliffords_to_h2(module)
    verify_module(module)

    assert not _has_cliffords(module)
    assert any(isinstance(op, (U1Op, RzOp, ZzOp)) for op in module.walk())

    histogram = dict(Machine(module, num_qubits=2).eval(shots=2000).histogram())
    assert set(histogram) <= {(0, 0), (1, 1)}
    for outcome in ((0, 0), (1, 1)):
        assert 800 < histogram.get(outcome, 0) < 1200


def test_rep3_to_h2_executes() -> None:
    module = compile_rep3_bit(lower(parse(_FLIP)))
    compile_cliffords_to_h2(module)
    verify_module(module)

    registry = CallbackRegistry()
    register_rep3_bit_callbacks(registry)
    results = Machine(module, num_qubits=3, registry=registry).eval(shots=100)
    assert all(result == [1] for result in results)
    assert not _has_cliffords(module)


def test_repeated_rep3_to_h2_executes() -> None:
    module = compile_rep3_bit(compile_rep3_bit(lower(parse(_FLIP))))
    compile_cliffords_to_h2(module)
    verify_module(module)

    registry = CallbackRegistry()
    register_rep3_bit_callbacks(registry)
    results = Machine(module, num_qubits=9, registry=registry).eval(shots=20)
    assert all(result == [1] for result in results)
    assert not _has_cliffords(module)


def test_rep3_bit_plus_phase_to_h2_executes() -> None:
    module = compile_rep3_phase(compile_rep3_bit(lower(parse(_FLIP))))
    compile_cliffords_to_h2(module)
    verify_module(module)

    registry = CallbackRegistry()
    register_rep3_bit_callbacks(registry)
    register_rep3_phase_callbacks(registry)
    results = Machine(module, num_qubits=9, registry=registry).eval(shots=20)
    assert all(result == [1] for result in results)
    assert not _has_cliffords(module)
