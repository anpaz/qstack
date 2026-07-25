"""Tests for the toy → cliffords rewrite pass (Phase 4.2)."""

import pytest

from qstack.dialect.cliffords import CxOp, HOp, XOp
from qstack.dialect.toy import EntangleOp, FlipOp, MixOp, SkewOp
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


def _all_ops(module):
    seen = []
    for fn in module.body.ops:
        for op in _walk(fn):
            seen.append(op)
    return seen


def _walk(op):
    yield op
    for region in op.regions:
        for block in region.blocks:
            for inner in block.ops:
                yield from _walk(inner)


def test_toy_bell_lowers_with_toy_ops() -> None:
    module = lower(parse(_TOY_BELL))
    types = {type(op).__name__ for op in _all_ops(module)}
    assert "MixOp" in types
    assert "EntangleOp" in types


def test_toy_to_cliffords_replaces_supported_ops() -> None:
    module = lower(parse(_TOY_BELL))
    compile_toy_to_cliffords(module)
    types = {type(op).__name__ for op in _all_ops(module)}
    assert "MixOp" not in types
    assert "FlipOp" not in types
    assert "EntangleOp" not in types
    assert "HOp" in types
    assert "CxOp" in types


def test_compiled_module_still_verifies_and_runs() -> None:
    module = lower(parse(_TOY_BELL))
    compile_toy_to_cliffords(module)
    verify_module(module)
    hist = dict(Machine(module, num_qubits=4).eval(shots=2000).histogram())
    # Same bell distribution as the original toy program.
    assert set(hist.keys()) <= {(0, 0), (1, 1)}
    for key in [(0, 0), (1, 1)]:
        assert (
            800 < hist.get(key, 0) < 1200
        ), f"clifford-compiled Bell outcome {key} count {hist.get(key, 0)} outside [800, 1200]"


def test_skew_rejection_is_explicit() -> None:
    src = """
QSTACKQASM 0.1;
include "qstack/toy.inc";

qreg q[1];
creg c[1];
skew(0.8) q[0];
measure q[0] -> c[0];
"""
    module = lower(parse(src))
    with pytest.raises(NotImplementedError, match="toy.skew"):
        compile_toy_to_cliffords(module)
