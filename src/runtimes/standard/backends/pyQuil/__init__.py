from qstack.backend import Outcome
from qstack.quantum_kernel import QuantumKernel
from runtimes.matrix.backends.pyQuil import Backend as PyQuilBackend

from compilers.standard.matrix.compiler import compile


class Backend(PyQuilBackend):

    def eval(self, kernel: QuantumKernel, *, shots: int | None = 10) -> Outcome:
        k2 = compile(kernel)
        return super().eval(k2, shots=shots)
