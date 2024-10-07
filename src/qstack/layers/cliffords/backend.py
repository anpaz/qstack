import qstack.backend

import qstack.gadget
from qstack.layers.stabilizer.backends import Backend as StabilizerBackend


class Backend(StabilizerBackend):

    def eval(self, gadget: qstack.gadget.Gadget, *, shots: int | None = 1000) -> qstack.backend.Outcome:
        return super().eval(gadget, shots=shots)
