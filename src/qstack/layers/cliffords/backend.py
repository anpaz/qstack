import qstack.backend

from qstack.layers.stabilizer.backends import Backend as StabilizerBackend


class Backend(StabilizerBackend):

    def eval(self, kernel: qstack.backend.QuantumKernel, *, shots: int | None = 1000) -> qstack.backend.Outcome:
        return super().eval(kernel, shots=shots)
