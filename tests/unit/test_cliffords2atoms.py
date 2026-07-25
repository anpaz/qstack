"""Tests for canonical Clifford to atoms lowering."""

import math

import numpy as np
from xdsl.dialects.builtin import FunctionType, ModuleOp
from xdsl.dialects.func import FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Block, Region

from qstack.dialect import QubitType
from qstack.dialect.atoms import CzOp as AtomsCzOp
from qstack.dialect.atoms import RzOp, SxOp
from qstack.dialect.atoms import CZ_MAT, SX_MAT, rz_matrix
from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, YOp, ZOp
from qstack.dialect.cliffords import H_MAT, X_MAT, Y_MAT, Z_MAT
from qstack.passes.cliffords2atoms import (
    CliffordsToAtomsCompiler,
    compile_cliffords_to_atoms,
)


def _equal_up_to_global_phase(actual: np.ndarray, expected: np.ndarray) -> bool:
    pivot = np.unravel_index(np.argmax(np.abs(expected)), expected.shape)
    phase = actual[pivot] / expected[pivot]
    return np.allclose(actual, phase * expected, atol=1e-10)


def test_single_qubit_decompositions_match_cliffords() -> None:
    x = SX_MAT @ SX_MAT
    y = rz_matrix(math.pi) @ SX_MAT @ SX_MAT
    z = rz_matrix(math.pi)
    s = rz_matrix(math.pi / 2)
    h = rz_matrix(math.pi / 2) @ SX_MAT @ rz_matrix(math.pi / 2)

    expected = {
        "x": X_MAT,
        "y": Y_MAT,
        "z": Z_MAT,
        "s": np.diag([1, 1j]).astype(complex),
        "h": H_MAT,
    }
    for name, actual in {"x": x, "y": y, "z": z, "s": s, "h": h}.items():
        assert _equal_up_to_global_phase(actual, expected[name]), name


def test_two_qubit_decompositions_match_cliffords() -> None:
    identity = np.eye(2, dtype=complex)
    h = rz_matrix(math.pi / 2) @ SX_MAT @ rz_matrix(math.pi / 2)
    cx = np.kron(identity, h) @ CZ_MAT @ np.kron(identity, h)

    expected_cx = np.array(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]],
        dtype=complex,
    )
    assert _equal_up_to_global_phase(CZ_MAT, np.diag([1, 1, 1, -1]).astype(complex))
    assert _equal_up_to_global_phase(cx, expected_cx)


def test_pass_rewrites_every_canonical_clifford() -> None:
    block = Block(arg_types=[QubitType(), QubitType()])
    q0, q1 = block.args
    for gate in (HOp, XOp, YOp, ZOp, SOp):
        op = gate(q0)
        block.add_op(op)
        q0 = op.result
    cz = CzOp(q0, q1)
    block.add_op(cz)
    cx = CxOp(cz.control_out, cz.target_out)
    block.add_op(cx)
    block.add_op(FuncReturn.create(operands=[cx.control_out, cx.target_out]))
    module = ModuleOp(
        [
            FuncOp(
                "gates",
                FunctionType.from_lists(
                    [QubitType(), QubitType()],
                    [QubitType(), QubitType()],
                ),
                Region([block]),
            )
        ]
    )

    compile_cliffords_to_atoms(module)

    assert not any(
        isinstance(op, (HOp, XOp, YOp, ZOp, SOp, CxOp, CzOp))
        for op in module.walk()
    )
    assert any(isinstance(op, RzOp) for op in module.walk())
    assert any(isinstance(op, SxOp) for op in module.walk())
    assert any(isinstance(op, AtomsCzOp) for op in module.walk())
    module.verify()


def test_compiler_dispatches_with_a_complete_handler_registry() -> None:
    assert set(CliffordsToAtomsCompiler().handlers) == {
        HOp,
        XOp,
        YOp,
        ZOp,
        SOp,
        CxOp,
        CzOp,
    }
