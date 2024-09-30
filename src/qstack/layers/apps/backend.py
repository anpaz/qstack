import qstack.backend

from qstack.layers.cliffords.compilers.apps.compiler import compile
from qstack.layers.stabilizer.backends import Backend as StabilizerBackend


class Backend(StabilizerBackend):

    def eval(self, kernel: qstack.backend.QuantumKernel, *, shots: int | None = 1000) -> qstack.backend.Outcome:
        kernel = compile(kernel)
        return super().eval(kernel, shots=shots)
