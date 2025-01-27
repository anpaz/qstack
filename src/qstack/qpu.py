from .layer import Layer
from .ast import Instruction


class QPU:

    @property
    def layer(self) -> Layer:
        pass

    def restart(self, num_qubits: int | None = None):
        pass

    def eval(self, instruction: Instruction):
        pass
