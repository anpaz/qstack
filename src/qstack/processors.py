import abc
from .ast import QuantumInstruction, QubitId, ClassicInstruction, Kernel

type Outcome = int


class QPU(abc.ABC):

    @abc.abstractmethod
    def restart(self, num_qubits: int):
        pass

    @abc.abstractmethod
    def allocate(self, target: QubitId):
        pass

    @abc.abstractmethod
    def eval(self, instruction: QuantumInstruction):
        pass

    @abc.abstractmethod
    def measure(self) -> Outcome:
        pass


class CPU(abc.ABC):

    @abc.abstractmethod
    def restart(self):
        pass

    @abc.abstractmethod
    def collect(self, result: Outcome):
        pass

    @abc.abstractmethod
    def consume(self) -> Outcome:
        pass

    @abc.abstractmethod
    def eval(self, instruction: ClassicInstruction) -> Kernel | None:
        pass


def flush(cpu: QPU):
    o = cpu.consume()
    while o is not None:
        yield o
        o = cpu.consume()
