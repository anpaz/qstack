from typing import Iterable, List, Sequence
from qstack.quantum_kernel import QuantumKernel

from runtimes.matrix.backends.pyQuil import Backend as PyQuilBackend
from compilers.standard.matrix.compiler import compile


class Backend:
    def start(self, memory_size: int | None = None) -> int:
        self.backend = PyQuilBackend()
        self.backend.start(memory_size)

    def eval(self, kernel: QuantumKernel, *, shots: int | None = 10) -> Iterable[List[bool]]:
        k2 = compile(kernel)
        for o in self.backend.eval(k2, shots=shots):
            yield o

    @property
    def memory(self) -> tuple[bool, ...]:
        return self.backend.memory
