from .layer import Layer
from .ast import Instruction, QubitId


class QPU:

    def restart(self, num_qubits: int):
        pass

    def allocate(self, target: QubitId) -> int:
        pass

    def eval(self, instruction: Instruction):
        pass

    def measure(self):
        pass
