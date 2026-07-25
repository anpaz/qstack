"""Tests for include-driven ISA gate resolution."""

from pathlib import Path

import pytest

from xdsl.dialects.func import CallOp

from qstack_mlir.dialect.cliffords import HOp
from qstack_mlir.dialect.toy import FlipOp, MixOp
from qstack_mlir.dialect.atoms import RzOp as AtomsRzOp
from qstack_mlir.dialect.h2 import RzOp as H2RzOp
from qstack_mlir.surface import isa_includes
from qstack_mlir.surface.lowering import lower
from qstack_mlir.surface.parser import parse


def _program(include: str) -> str:
    return f"""
QSTACKQASM 0.1;
include "{include}";

qreg q[1];
creg c[1];
rz(0.25) q[0];
measure q[0] -> c[0];
"""


def test_h2_include_resolves_rz_to_h2_rz() -> None:
    module = lower(parse(_program("qstack/h2.inc")))
    assert any(isinstance(op, H2RzOp) for op in module.walk())
    assert not any(isinstance(op, AtomsRzOp) for op in module.walk())


def test_atoms_include_resolves_rz_to_atoms_rz() -> None:
    module = lower(parse(_program("qstack/atoms.inc")))
    assert any(isinstance(op, AtomsRzOp) for op in module.walk())
    assert not any(isinstance(op, H2RzOp) for op in module.walk())


def test_gate_not_declared_by_active_include_fails() -> None:
    with pytest.raises(NotImplementedError, match="not declared"):
        lower(
            parse(
                """
QSTACKQASM 0.1;
include "qstack/atoms.inc";
qreg q[2];
creg c[2];
cx q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""
            )
        )


def test_user_def_shadows_included_isa_gate() -> None:
    module = lower(
        parse(
            """
QSTACKQASM 0.1;
include "qstack/toy.inc";

def flip(qubit q) {
}

qreg q[1];
creg c[1];
flip q[0];
measure q[0] -> c[0];
"""
        )
    )

    assert any(
        isinstance(op, CallOp) and op.callee.string_value() == "flip"
        for op in module.walk()
    )
    assert not any(isinstance(op, FlipOp) for op in module.walk())


def test_multiple_includes_with_disjoint_gate_names_resolve() -> None:
    module = lower(
        parse(
            """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";
include "qstack/toy.inc";
qreg q[1];
creg c[1];
h q[0];
mix q[0];
measure q[0] -> c[0];
"""
        )
    )

    assert any(isinstance(op, HOp) for op in module.walk())
    assert any(isinstance(op, MixOp) for op in module.walk())


def test_duplicate_gate_names_across_includes_fail() -> None:
    with pytest.raises(ValueError, match="declared by multiple ISA includes"):
        lower(
            parse(
                """
QSTACKQASM 0.1;
include "qstack/h2.inc";
include "qstack/atoms.inc";
qreg q[1];
creg c[1];
measure q[0] -> c[0];
"""
            )
        )


def test_include_declared_gate_must_have_matching_op(monkeypatch, tmp_path: Path) -> None:
    include_dir = tmp_path / "includes"
    include_dir.mkdir()
    (include_dir / "bad.inc").write_text(
        "#pragma qstack.isa h2;\n"
        "gate missing q;\n"
    )
    monkeypatch.setattr(isa_includes, "_INCLUDE_DIR", include_dir)

    with pytest.raises(ValueError, match="h2.missing"):
        lower(
            parse(
                """
QSTACKQASM 0.1;
include "qstack/bad.inc";
qreg q[1];
creg c[1];
measure q[0] -> c[0];
"""
            )
        )


def test_include_declared_params_must_match_op_properties(monkeypatch, tmp_path: Path) -> None:
    include_dir = tmp_path / "includes"
    include_dir.mkdir()
    (include_dir / "bad.inc").write_text(
        "#pragma qstack.isa h2;\n"
        "gate rz(phi) q;\n"
    )
    monkeypatch.setattr(isa_includes, "_INCLUDE_DIR", include_dir)

    with pytest.raises(ValueError, match="properties"):
        lower(
            parse(
                """
QSTACKQASM 0.1;
include "qstack/bad.inc";
qreg q[1];
creg c[1];
measure q[0] -> c[0];
"""
            )
        )
