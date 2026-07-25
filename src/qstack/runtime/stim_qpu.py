"""STIM QPU implementation."""

from __future__ import annotations

import logging

import stim

from qstack_mlir.runtime.qpu import GateApplication

logger = logging.getLogger("qstack")


class StimQPU:
    """STIM-backed QPU for on-the-fly Clifford execution."""

    def __init__(
        self,
        num_qubits: int,
        *,
        seed: int | None = None,
    ) -> None:
        self._num_qubits = num_qubits
        self._rng_seed = seed
        self._sim: stim.TableauSimulator | None = None
        self._free: list[int] = []

    def restart(self) -> None:
        logger.debug("stim_qpu.restart: %s", self._num_qubits)
        kwargs = {"seed": self._rng_seed} if self._rng_seed is not None else {}
        self._sim = stim.TableauSimulator(**kwargs)
        self._free = list(reversed(range(self._num_qubits)))

    def allocate(self) -> int:
        if not self._free:
            raise RuntimeError("qpu out of physical qubits")
        idx = self._free.pop()
        if self._sim is None:
            raise RuntimeError("qpu has not been restarted")
        self._sim.reset(idx)
        return idx

    def release(self, idx: int) -> None:
        self._free.append(idx)

    def measure(self, idx: int) -> int:
        if self._sim is None:
            raise RuntimeError("qpu has not been restarted")
        outcome = int(self._sim.measure(idx))
        logger.debug("stim_qpu.measure: %s -> %s", idx, outcome)
        self._sim.reset(idx)
        self.release(idx)
        return outcome

    def apply_gate(self, gate: GateApplication) -> None:
        if self._sim is None:
            raise RuntimeError("qpu has not been restarted")
        qubits = gate.qubits
        logger.debug(
            "stim_qpu.eval: %s %s",
            gate.op.name.rsplit(".", 1)[-1],
            list(qubits),
        )
        if gate.op.name == "cliffords.h":
            self._sim.h(*qubits)
        elif gate.op.name == "cliffords.x":
            self._sim.x(*qubits)
        elif gate.op.name == "cliffords.y":
            self._sim.y(*qubits)
        elif gate.op.name == "cliffords.z":
            self._sim.z(*qubits)
        elif gate.op.name == "cliffords.s":
            self._sim.s(*qubits)
        elif gate.op.name == "cliffords.cx":
            self._sim.cx(*qubits)
        elif gate.op.name == "cliffords.cz":
            self._sim.cz(*qubits)
        else:
            raise RuntimeError(f"StimQPU does not support gate {gate.op.name}")
