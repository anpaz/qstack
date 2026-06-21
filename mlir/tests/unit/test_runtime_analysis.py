"""Tests for runtime backend-compatibility analysis."""

from qstack_mlir.passes.toy2cliffords import compile_toy_to_cliffords
from qstack_mlir.runtime.analysis import check_stim_compatible, is_stim_compatible
from qstack_mlir.surface.lowering import lower
from qstack_mlir.surface.parser import parse


def _lower(source: str):
    return lower(parse(source))


def test_clifford_module_is_stim_compatible() -> None:
    module = _lower(
        """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[2];
creg c[2];
h q[0];
cx q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""
    )

    assert is_stim_compatible(module)


def test_non_clifford_dialect_is_not_stim_compatible() -> None:
    module = _lower(
        """
QSTACKQASM 0.1;
include "qstack/atoms.inc";

qreg q[1];
creg c[1];
sx q[0];
measure q[0] -> c[0];
"""
    )

    result = check_stim_compatible(module)

    assert not result.ok
    assert result.reason is not None
    assert "atoms.sx" in result.reason


def test_toy_module_becomes_stim_compatible_after_lowering_to_cliffords() -> None:
    module = _lower(
        """
QSTACKQASM 0.1;
include "qstack/toy.inc";

qreg q[2];
creg c[2];
mix q[0];
entangle q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""
    )

    assert not is_stim_compatible(module)

    compile_toy_to_cliffords(module)

    assert is_stim_compatible(module)
