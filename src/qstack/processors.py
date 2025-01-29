from .ast import QuantumInstruction, QubitId, ClassicInstruction, Kernel

type Outcome = int


class QPU:

    def restart(self, num_qubits: int):
        pass

    def allocate(self, target: QubitId):
        pass

    def eval(self, instruction: QuantumInstruction):
        pass

    def measure(self) -> Outcome:
        pass


class CPU:

    def restart(self):
        pass

    def collect(self, result: Outcome):
        pass

    def consume(self) -> Outcome:
        pass

    def eval(self, instruction: ClassicInstruction) -> Kernel:
        pass
