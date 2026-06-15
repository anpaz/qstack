"""Thin shots-loop wrapper over the emulator.

A ``Machine`` bundles a ``ModuleOp`` and a ``CallbackRegistry`` with a
fixed physical-qubit budget and exposes a ``shots(name, count)`` helper
that runs ``func.func @name`` ``count`` times and collects the results.
"""

from __future__ import annotations

from typing import Any

from xdsl.dialects.builtin import ModuleOp

from qstack_mlir.runtime.emulator import Emulator
from qstack_mlir.runtime.noise import NoiseChannel
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
        self._registry = registry
        self._num_qubits = num_qubits
        self._seed = seed
        self._noise = noise

    def shots(self, name: str, count: int, *, args: list[Any] | None = None) -> Results:
        """Run ``@name`` ``count`` times. Returns a :class:`Results` wrapper."""
        out: list[list[int | None]] = []
        for _ in range(count):
            emu = Emulator(
                num_qubits=self._num_qubits,
                module=self._module,
                registry=self._registry,
                seed=self._seed,
                noise=self._noise,
            )
            out.append(emu.run_func(name, args=args))
        return Results(out)
