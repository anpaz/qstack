"""Hybrid quantum machine for qstack MLIR execution.

A ``Machine`` is composed of a QPU and CPU so programs can mix quantum
state evolution with classical callback-driven control. It binds that
processor pair to a ``ModuleOp`` and fixed physical-qubit budget, then
exposes ``single_shot`` and ``eval`` helpers.
"""

from __future__ import annotations

from typing import Any

from xdsl.dialects.builtin import ModuleOp

from qstack_mlir.runtime.evaluator import ModuleEvaluator
from qstack_mlir.runtime.noise import NoiseChannel
from qstack_mlir.runtime.processors import CPU, QPU
from qstack_mlir.runtime.registry import CallbackRegistry
from qstack_mlir.runtime.results import Results


class Machine:
    def __init__(
        self,
        module: ModuleOp,
        *,
        num_qubits: int,
        registry: CallbackRegistry | None = None,
        seed: int | None = None,
        noise: NoiseChannel | None = None,
    ) -> None:
        self._module = module
        self._num_qubits = num_qubits
        self.qpu = QPU(num_qubits, seed=seed, noise=noise)
        self.cpu = CPU(registry)

    def single_shot(
        self,
        name: str = "main",
        *,
        args: list[Any] | None = None,
    ) -> list[int | None]:
        """Run ``@name`` once from a fresh simulator state."""
        return self._evaluator().run_func(name, args=args)

    def eval(
        self,
        name: str = "main",
        *,
        shots: int = 1000,
        args: list[Any] | None = None,
    ) -> Results:
        """Run ``@name`` ``shots`` times and collect the returned bits."""
        return Results([self.single_shot(name, args=args) for _ in range(shots)])

    def _evaluator(self) -> ModuleEvaluator:
        return ModuleEvaluator(
            num_qubits=self._num_qubits,
            module=self._module,
            qpu=self.qpu,
            cpu=self.cpu,
        )
