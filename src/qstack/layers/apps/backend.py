import qstack.backend

from qstack.layers.cliffords.compilers.apps.compiler import compile
from qstack.layers.stabilizer.backends import Backend as StabilizerBackend


class Backend(StabilizerBackend):

    def eval(self, gadget: qstack.backend.Gadget, *, shots: int | None = 1000) -> qstack.backend.Outcome:
        gadget = compile(gadget)
        return super().eval(gadget, shots=shots)
