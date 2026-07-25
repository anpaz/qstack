"""Tests for the noisy runtime path."""

import numpy as np

from qstack_mlir.runtime import CallbackRegistry, Machine
from qstack_mlir.runtime.noise import DepolarizingNoise, NoiselessChannel
from qstack_mlir.surface.lowering import lower
from qstack_mlir.surface.parser import parse

BELL_PROGRAM = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[2];
creg c[2];
h q[0];
cx q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""


def test_noiseless_channel_kraus_is_identity() -> None:
    chan = NoiselessChannel()
    [k] = chan.get_kraus_matrices(dim=2)
    np.testing.assert_array_equal(k, np.eye(2))


def test_depolarizing_kraus_count_matches_dim() -> None:
    chan = DepolarizingNoise(0.3)
    # 1 identity-scaled term plus d*(d-1) off-diagonal ladder operators.
    assert len(chan.get_kraus_matrices(dim=2)) == 1 + 2 * 1
    assert len(chan.get_kraus_matrices(dim=4)) == 1 + 4 * 3


def test_noiseless_machine_matches_existing_bell() -> None:
    module = lower(parse(BELL_PROGRAM))
    machine = Machine(
        module,
        num_qubits=4,
        registry=CallbackRegistry(),
        noise=NoiselessChannel(),
    )
    hist = dict(machine.eval(shots=4000).histogram())
    # Without noise, the Bell histogram concentrates on (0,0) and (1,1).
    assert set(hist.keys()) == {(0, 0), (1, 1)}


def test_depolarizing_noise_smears_bell_distribution() -> None:
    module = lower(parse(BELL_PROGRAM))
    machine = Machine(
        module,
        num_qubits=4,
        registry=CallbackRegistry(),
        noise=DepolarizingNoise(0.5),
    )
    hist = dict(machine.eval(shots=4000).histogram())
    # With p=0.5 depolarizing noise on every gate, the off-diagonal
    # outcomes (0,1) and (1,0) must appear with non-negligible weight.
    off_diag = hist.get((0, 1), 0) + hist.get((1, 0), 0)
    assert off_diag > 400, f"expected substantial off-diagonal weight; got {hist!r}"
