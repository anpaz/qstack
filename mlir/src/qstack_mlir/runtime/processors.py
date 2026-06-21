"""Classical and quantum processors used by the MLIR runtime."""

from __future__ import annotations

import logging
import random

import numpy as np
from qsharp.noisy_simulator import Instrument, Operation, StateVectorSimulator
from xdsl.dialects.func import FuncOp

from qstack_mlir.dialect.core import DecodeOp, SelectOp
from qstack_mlir.runtime.noise import NoiseChannel, NoiselessChannel
from qstack_mlir.runtime.registry import CallbackRegistry

logger = logging.getLogger("qstack")

_RESET_X_MAT = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=complex)

_Z_INSTRUMENT = Instrument(
    [
        Operation([[[1.0, 0.0], [0.0, 0.0]]]),
        Operation([[[0.0, 0.0], [0.0, 1.0]]]),
    ]
)


class QPU:
    """Owns quantum state.

    Qubit allocation, unitary application, measurement, reset, and quantum
    noise are QPU responsibilities because they mutate or observe that state.
    """

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
        logger.debug("qpu.restart: %s", self._num_qubits)
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
        logger.debug("qpu.measure: %s -> %s", idx, outcome)
        if outcome == 1:
            self._sim.apply_operation(self._gate_op("x", _RESET_X_MAT), [idx])
        self.release(idx)
        return outcome

    def apply_unitary(self, name: str, unitary: np.ndarray, qubits: list[int]) -> None:
        if self._sim is None:
            raise RuntimeError("qpu has not been restarted")
        logger.debug("qpu.eval: %s %s", name, qubits)
        self._sim.apply_operation(self._gate_op(name, unitary), qubits)

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


class CPU:
    """Owns classical runtime state and callback evaluation.

    ``qstack.select`` and ``qstack.decode`` are CPU responsibilities because
    they evaluate classical state through host-language callbacks.
    """

    def __init__(self, registry: CallbackRegistry | None = None) -> None:
        self._registry = registry if registry is not None else CallbackRegistry()

    def restart(self) -> None:
        logger.debug("cpu.restart")

    def select(self, op: SelectOp, bit_values: dict[str, int], funcs: dict[str, FuncOp]) -> FuncOp:
        sym = op.callee.root_reference.data
        fn = self._registry.get_selector(sym)
        label = fn(**bit_values)
        logger.debug("cpu.select: %s %s -> %s", sym, bit_values, label)
        if label not in op.continuations.data:
            raise RuntimeError(
                f"selector @{sym} returned label {label!r} not in menu "
                f"{list(op.continuations.data)}"
            )
        cont_sym = op.continuations.data[label]
        cont_name = cont_sym.root_reference.data
        if cont_name not in funcs:
            raise RuntimeError(f"continuation @{cont_name} not in module")
        return funcs[cont_name]

    def decode(self, op: DecodeOp, args: list[int]) -> int:
        sym = op.callee.root_reference.data
        fn = self._registry.get_decoder(sym)
        result = int(fn(*args))
        logger.debug("cpu.decode: %s %s -> %s", sym, args, result)
        return result
