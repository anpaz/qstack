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
    def eval(self, instruction: ClassicInstruction | None, outcome: Outcome | None) -> Kernel | None:
        pass

    @property
    @abc.abstractmethod
    def context(self):
        pass
