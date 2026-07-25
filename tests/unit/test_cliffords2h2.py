"""Tests for canonical Clifford to H2 lowering."""

import math

import numpy as np
from xdsl.dialects.builtin import FunctionType, ModuleOp
from xdsl.dialects.func import FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Block, Region

from qstack_mlir.dialect import QubitType
from qstack_mlir.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, YOp, ZOp
from qstack_mlir.dialect.h2 import RzOp, U1Op, ZzOp
from qstack_mlir.passes.cliffords2h2 import (
    CliffordsToH2Compiler,
    compile_cliffords_to_h2,
)


def _u1(theta: float, phi: float) -> np.ndarray:
    c = math.cos(theta / 2)
    s = math.sin(theta / 2)
    return np.array(
        [
            [c, -1j * np.exp(-1j * phi) * s],
            [-1j * np.exp(1j * phi) * s, c],
        ],
        dtype=complex,
    )


def _rz(theta: float) -> np.ndarray:
    return np.diag(
        [np.exp(-1j * theta / 2), np.exp(1j * theta / 2)]
    ).astype(complex)


def _zz() -> np.ndarray:
    phase = np.exp(-1j * math.pi / 4)
    return np.diag([phase, 1j * phase, 1j * phase, phase]).astype(complex)


def _equal_up_to_global_phase(actual: np.ndarray, expected: np.ndarray) -> bool:
    pivot = np.unravel_index(np.argmax(np.abs(expected)), expected.shape)
    phase = actual[pivot] / expected[pivot]
    return np.allclose(actual, phase * expected, atol=1e-10)


def test_single_qubit_decompositions_match_cliffords() -> None:
    x = _u1(math.pi, 0)
    y = _u1(math.pi, math.pi / 2)
    z = _rz(math.pi)
    s = _rz(math.pi / 2)
    h = _rz(math.pi) @ _u1(math.pi / 2, -math.pi / 2)

    expected = {
        "x": np.array([[0, 1], [1, 0]], dtype=complex),
        "y": np.array([[0, -1j], [1j, 0]], dtype=complex),
        "z": np.diag([1, -1]).astype(complex),
        "s": np.diag([1, 1j]).astype(complex),
        "h": np.array([[1, 1], [1, -1]], dtype=complex) / math.sqrt(2),
    }
    for name, actual in {"x": x, "y": y, "z": z, "s": s, "h": h}.items():
        assert _equal_up_to_global_phase(actual, expected[name]), name


def test_two_qubit_decompositions_match_cliffords() -> None:
    identity = np.eye(2, dtype=complex)
    h = _rz(math.pi) @ _u1(math.pi / 2, -math.pi / 2)
    local_rz = np.kron(_rz(-math.pi / 2), _rz(-math.pi / 2))
    cz = local_rz @ _zz()
    cx = np.kron(identity, h) @ cz @ np.kron(identity, h)

    expected_cz = np.diag([1, 1, 1, -1]).astype(complex)
    expected_cx = np.array(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]],
        dtype=complex,
    )
    assert _equal_up_to_global_phase(cz, expected_cz)
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

    compile_cliffords_to_h2(module)

    assert not any(
        isinstance(op, (HOp, XOp, YOp, ZOp, SOp, CxOp, CzOp))
        for op in module.walk()
    )
    assert any(isinstance(op, U1Op) for op in module.walk())
    assert any(isinstance(op, RzOp) for op in module.walk())
    assert any(isinstance(op, ZzOp) for op in module.walk())
    module.verify()


def test_compiler_dispatches_with_a_complete_handler_registry() -> None:
    assert set(CliffordsToH2Compiler().handlers) == {
        HOp,
        XOp,
        YOp,
        ZOp,
        SOp,
        CxOp,
        CzOp,
    }
