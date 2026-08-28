"""Hybrid quantum machine for qstack MLIR execution.

A ``Machine`` is composed of a QPU and CPU so programs can mix quantum
state evolution with classical callback-driven control. It binds that
processor pair to a ``ModuleOp`` and fixed physical-qubit budget, then
exposes ``single_shot`` and ``eval`` helpers.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from xdsl.dialects.builtin import ModuleOp

from qstack.runtime.analysis import StimCompatibilityError, check_stim_compatible
from qstack.runtime.cpu import CPU
from qstack.runtime.evaluator import ModuleEvaluator
from qstack.runtime.noise import NoiseChannel
from qstack.runtime.qpu import QPUProtocol
from qstack.runtime.registry import CallbackRegistry
from qstack.runtime.results import Results
from qstack.runtime.statevector_qpu import StateVectorQPU
from qstack.runtime.stim_qpu import StimQPU

QPUSelection = Literal["auto", "statevector", "stim"]
logger = logging.getLogger("qstack")


class Machine:
    def __init__(
        self,
        module: ModuleOp,
        *,
        num_qubits: int,
        registry: CallbackRegistry | None = None,
        seed: int | None = None,
        noise: NoiseChannel | None = None,
        qpu: QPUSelection | QPUProtocol = "auto",
    ) -> None:
        self._module = module
        self._num_qubits = num_qubits
        self.qpu = self._build_qpu(qpu=qpu, seed=seed, noise=noise)
        logger.debug(
            "machine.qpu: selected %s (requested=%s, num_qubits=%s, legacy_noise=%s)",
            type(self.qpu).__name__,
            qpu if isinstance(qpu, str) else "user",
            num_qubits,
            noise is not None,
        )
        self.cpu = CPU(registry)

    def single_shot(self) -> list[int]:
        """Run the unique ``qstack.kernel @main`` once."""
        return self._evaluator().run_main()

    def eval(
        self,
        *,
        shots: int = 1000,
    ) -> Results:
        """Run ``@main`` ``shots`` times and collect its returned bits."""
        return Results([self.single_shot() for _ in range(shots)])

    def _evaluator(self) -> ModuleEvaluator:
        return ModuleEvaluator(
            num_qubits=self._num_qubits,
            module=self._module,
            qpu=self.qpu,
            cpu=self.cpu,
        )

    def _build_qpu(
        self,
        *,
        qpu: QPUSelection | QPUProtocol,
        seed: int | None,
        noise: NoiseChannel | None,
    ) -> QPUProtocol:
        if not isinstance(qpu, str):
            if noise is not None:
                raise ValueError("noise= cannot be combined with a user-supplied qpu")
            return qpu

        if qpu not in {"auto", "statevector", "stim"}:
            raise ValueError(f"unknown qpu selection {qpu!r}")

        has_legacy_noise_arg = noise is not None
        if qpu == "statevector":
            return StateVectorQPU(self._num_qubits, seed=seed, noise=noise)

        compatibility = check_stim_compatible(self._module)
        if qpu == "stim":
            if has_legacy_noise_arg:
                raise StimCompatibilityError("StimQPU does not support legacy NoiseChannel")
            if not compatibility.ok:
                raise StimCompatibilityError(compatibility.reason or "module is not STIM-compatible")
            return StimQPU(self._num_qubits, seed=seed)

        if compatibility.ok and not has_legacy_noise_arg:
            return StimQPU(self._num_qubits, seed=seed)
        return StateVectorQPU(self._num_qubits, seed=seed, noise=noise)
