from abc import ABC, abstractmethod
from qcir.circuit import Circuit
from qstack.instruction_definition import InstructionDefinition


class Emulator(ABC):
    @property
    @abstractmethod
    def instruction_set(self) -> set[InstructionDefinition]:
        pass

    @abstractmethod
    def eval(circuit: Circuit, *, shots: int):
        pass
