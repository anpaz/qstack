"""End-to-end parity pipelines ending in the H2-native dialect."""

from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, YOp, ZOp
from qstack.dialect.h2 import RzOp, U1Op, ZzOp
from qstack.passes.cliffords2h2 import lower_cliffords_to_h2
from qstack.passes.rep3_bit import lower_rep3_bit
from qstack.passes.rep3_phase import lower_rep3_phase
from qstack.passes.toy2cliffords import lower_toy_to_cliffords
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
    module = lower_toy_to_cliffords(module)
    module = lower_cliffords_to_h2(module)
    verify_module(module)

    assert not _has_cliffords(module)
    assert any(isinstance(op, (U1Op, RzOp, ZzOp)) for op in module.walk())

    histogram = dict(Machine(num_qubits=2).eval(module, shots=2000).histogram())
    assert set(histogram) <= {(0, 0), (1, 1)}
    for outcome in ((0, 0), (1, 1)):
        assert 800 < histogram.get(outcome, 0) < 1200


def test_rep3_to_h2_executes() -> None:
    registry = CallbackRegistry()
    module = lower_rep3_bit(lower(parse(_FLIP)), registry)
    module = lower_cliffords_to_h2(module)
    verify_module(module)

    results = Machine(num_qubits=3, registry=registry).eval(module, shots=100)
    assert all(result == [1] for result in results)
    assert not _has_cliffords(module)


def test_repeated_rep3_to_h2_executes() -> None:
    registry = CallbackRegistry()
    module = lower_rep3_bit(
        lower_rep3_bit(lower(parse(_FLIP)), registry), registry
    )
    module = lower_cliffords_to_h2(module)
    verify_module(module)

    results = Machine(num_qubits=9, registry=registry).eval(module, shots=20)
    assert all(result == [1] for result in results)
    assert not _has_cliffords(module)


def test_rep3_bit_plus_phase_to_h2_executes() -> None:
    registry = CallbackRegistry()
    module = lower_rep3_phase(
        lower_rep3_bit(lower(parse(_FLIP)), registry), registry
    )
    module = lower_cliffords_to_h2(module)
    verify_module(module)

    results = Machine(num_qubits=9, registry=registry).eval(module, shots=20)
    assert all(result == [1] for result in results)
    assert not _has_cliffords(module)
