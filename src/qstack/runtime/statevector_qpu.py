"""State-vector QPU implementation."""

from __future__ import annotations

import logging
import random

import numpy as np
from qsharp.noisy_simulator import Instrument, Operation, StateVectorSimulator

from qstack_mlir.dialect.core import UnitaryGateOp
from qstack_mlir.runtime.noise import NoiseChannel, NoiselessChannel
from qstack_mlir.runtime.qpu import GateApplication

logger = logging.getLogger("qstack")

_RESET_X_MAT = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=complex)

_Z_INSTRUMENT = Instrument(
    [
        Operation([[[1.0, 0.0], [0.0, 0.0]]]),
        Operation([[[0.0, 0.0], [0.0, 1.0]]]),
    ]
)


class StateVectorQPU:
    """Owns quantum state for matrix/Kraus simulation."""

    def __init__(
        self,
        num_qubits: int,
        *,
        seed: int | None = None,
        noise: NoiseChannel | None = None,
    ) -> None:
        self._num_qubits = num_qubits
        self._rng_seed = seed
        self._noise: NoiseChannel = noise if noise is not None else NoiselessChannel()
        self._sim: StateVectorSimulator | None = None
        self._free: list[int] = []
        self._op_cache: dict[tuple[str, int], Operation] = {}

    def restart(self) -> None:
        seed = self._rng_seed if self._rng_seed is not None else random.randint(0, 2**31 - 1)
        logger.debug("statevector_qpu.restart: %s", self._num_qubits)
        self._sim = StateVectorSimulator(self._num_qubits, seed=seed)
        self._free = list(reversed(range(self._num_qubits)))

    def allocate(self) -> int:
        if not self._free:
            raise RuntimeError("qpu out of physical qubits")
        return self._free.pop()

    def release(self, idx: int) -> None:
        self._free.append(idx)

    def measure(self, idx: int) -> int:
        if self._sim is None:
            raise RuntimeError("qpu has not been restarted")
        outcome = int(self._sim.sample_instrument(_Z_INSTRUMENT, [idx]))
        logger.debug("statevector_qpu.measure: %s -> %s", idx, outcome)
        if outcome == 1:
            self._sim.apply_operation(self._gate_op("x", _RESET_X_MAT), [idx])
        self.release(idx)
        return outcome

    def apply_gate(self, gate: GateApplication) -> None:
        unitary = gate.op.unitary()
        name = self._semantic_cache_key(gate.op)
        qubits = list(gate.qubits)
        if len(qubits) == 2:
            # qsharp.noisy_simulator expects qubit list with target first when
            # the operation matrix is written in standard "control ⊗ target"
            # tensor order with little-endian wire indexing. The evaluator
            # passes qubits in operation operand order.
            qubits = [qubits[1], qubits[0]]
        self.apply_unitary(name, unitary, qubits)

    def apply_unitary(self, name: str, unitary: np.ndarray, qubits: list[int]) -> None:
        if self._sim is None:
            raise RuntimeError("qpu has not been restarted")
        logger.debug("statevector_qpu.eval: %s %s", name, qubits)
        self._sim.apply_operation(self._gate_op(name, unitary), qubits)

    @staticmethod
    def _semantic_cache_key(op: UnitaryGateOp) -> str:
        values = []
        for name, attr in sorted(op.properties.items()):
            value = getattr(getattr(attr, "value", None), "data", attr)
            values.append((name, value))
        if not values:
            return op.name.rsplit(".", 1)[-1]
        return f"{op.name}{tuple(values)}"

    def _gate_op(self, name: str, unitary: np.ndarray) -> Operation:
        dim = unitary.shape[0]
        key = (name, dim)
        cached = self._op_cache.get(key)
        if cached is not None:
            return cached
        kraus = self._noise.get_kraus_matrices(dim)
        op = Operation([K @ unitary for K in kraus])
        self._op_cache[key] = op
        return op
