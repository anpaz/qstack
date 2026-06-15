"""Noise channels for the qstack_mlir emulator.

A :class:`NoiseChannel` produces a list of Kraus matrices for an operation
of a given Hilbert-space dimension (``dim = 2**arity``).  The emulator
composes these with each gate's unitary as
``Operation([K @ U for K in kraus])`` and lets the underlying
``qsharp.noisy_simulator`` sample a Kraus branch per gate application.

Mirrors :mod:`qstack.noise` from the legacy stack but operates on raw
dimensions rather than ``QuantumDefinition``, since in the MLIR runtime
the gate arity is determined directly from the dialect.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class NoiseChannel(ABC):
    """Abstract base class: returns Kraus matrices for a ``dim×dim`` op."""

    @abstractmethod
    def get_kraus_matrices(self, dim: int) -> list[np.ndarray]:
        """Return Kraus operators for an operation acting on ``dim`` levels."""


class NoiselessChannel(NoiseChannel):
    """Identity channel — equivalent to running the noiseless emulator."""

    def get_kraus_matrices(self, dim: int) -> list[np.ndarray]:
        return [np.eye(dim)]


class DepolarizingNoise(NoiseChannel):
    """Depolarizing channel with total error probability ``p``.

    With probability ``1 - p`` the gate is applied noiselessly; otherwise
    the state is replaced by the maximally mixed state.  Constructed here
    in the off-diagonal ladder-operator basis used by the legacy
    :class:`qstack.noise.DepolarizingNoise`, which is trace-preserving.
    """

    def __init__(self, error_probability: float) -> None:
        if not 0.0 <= error_probability <= 1.0:
            raise ValueError("error_probability must lie in [0, 1]")
        self.error_probability = float(error_probability)

    def get_kraus_matrices(self, dim: int) -> list[np.ndarray]:
        p = self.error_probability
        kraus: list[np.ndarray] = [np.sqrt(1 - p) * np.eye(dim)]
        # d*(d-1) off-diagonal ladder operators, each with squared weight
        # p / (d*(d-1)); together they map any state to the maximally
        # mixed state when summed.
        scale = np.sqrt(p / (dim * (dim - 1))) if dim > 1 else 0.0
        for i in range(dim):
            for j in range(dim):
                if i == j:
                    continue
                m = np.zeros((dim, dim))
                m[i, j] = scale
                kraus.append(m)
        return kraus
