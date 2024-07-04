from abc import ABC, abstractmethod
from qcir.circuit import Circuit


class Emulator(ABC):

    @abstractmethod
    def eval(circuit: Circuit, *, shots: int):
        pass
