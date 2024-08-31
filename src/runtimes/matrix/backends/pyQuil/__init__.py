from typing import Iterable, List
from qstack.quantum_kernel import QuantumKernel
from .emulator import pyQuilEmulator as Emulator


class Backend:

    def start(self, memory_size: int | None = None) -> int:
        size = memory_size or 1
        self._memory = (False,) * size
        return 0

    def eval(self, kernel: QuantumKernel, *, shots: int | None = 10) -> Iterable[List[bool]]:
        init_memory = self._memory

        if kernel.register_count > len(self._memory):
            init_memory = self._memory + ((False,)) * (kernel.register_count - len(self._memory))

        emulator = Emulator()
        outcomes = list(emulator.eval(kernel.circuit, shots=shots, memory=init_memory))
        for outcome in outcomes:
            outcome = kernel.decoder(outcome)
            if outcome is not None:
                self._memory = tuple(outcome)
                yield outcome

    @property
    def memory(self) -> tuple[bool, ...]:
        return self._memory
