"""Hybrid quantum machine for qstack MLIR execution.

A ``Machine`` is composed of a QPU and CPU so programs can mix quantum
state evolution with classical callback-driven control. It owns a fixed
physical-qubit budget and evaluates any compatible ``ModuleOp`` passed to
``single_shot`` or ``eval``.
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

QPUSelection = Literal["statevector", "stim"]
logger = logging.getLogger("qstack")


class Machine:
    def __init__(
        self,
        *,
        num_qubits: int,
        registry: CallbackRegistry | None = None,
        seed: int | None = None,
        noise: NoiseChannel | None = None,
        qpu: QPUSelection | QPUProtocol | None = None,
    ) -> None:
        self._num_qubits = num_qubits
        self._qpu_selection = qpu
        self._seed = seed
        self._noise = noise
        self._qpus: dict[str, QPUProtocol] = {}
        if qpu is not None and not isinstance(qpu, str):
            if noise is not None:
                raise ValueError("noise= cannot be combined with a user-supplied qpu")
            self._qpus["user"] = qpu
        elif isinstance(qpu, str) and qpu not in {"statevector", "stim"}:
            raise ValueError(f"unknown qpu selection {qpu!r}")
        elif qpu == "stim" and noise is not None:
            raise StimCompatibilityError("StimQPU does not support legacy NoiseChannel")
        self.cpu = CPU(registry)

    def single_shot(self, module: ModuleOp) -> list[int]:
        """Run the unique ``qstack.kernel @main`` once."""
        return self._evaluator(module).run_main()

    def eval(
        self,
        module: ModuleOp,
        *,
        shots: int = 1000,
    ) -> Results:
        """Run ``@main`` ``shots`` times and collect its returned bits."""
        evaluator = self._evaluator(module)
        return Results([evaluator.run_main() for _ in range(shots)])

    def _evaluator(self, module: ModuleOp) -> ModuleEvaluator:
        return ModuleEvaluator(
            num_qubits=self._num_qubits,
            module=module,
            qpu=self._qpu_for(module),
            cpu=self.cpu,
        )

    def _qpu_for(self, module: ModuleOp) -> QPUProtocol:
        requested = self._qpu_selection
        if requested is not None and not isinstance(requested, str):
            return self._qpus["user"]

        selection = requested
        if selection is None:
            if self._noise is not None:
                selection = "statevector"
            else:
                compatibility = check_stim_compatible(module)
                selection = "stim" if compatibility.ok else "statevector"
        elif selection == "stim":
            compatibility = check_stim_compatible(module)
            if not compatibility.ok:
                raise StimCompatibilityError(
                    compatibility.reason or "module is not STIM-compatible"
                )

        if selection not in self._qpus:
            if selection == "stim":
                self._qpus[selection] = StimQPU(
                    self._num_qubits, seed=self._seed
                )
            else:
                self._qpus[selection] = StateVectorQPU(
                    self._num_qubits, seed=self._seed, noise=self._noise
                )
        qpu = self._qpus[selection]
        logger.debug(
            "machine.qpu: selected %s (requested=%s, num_qubits=%s, legacy_noise=%s)",
            type(qpu).__name__,
            "per-evaluation" if requested is None else requested,
            self._num_qubits,
            self._noise is not None,
        )
        return qpu
