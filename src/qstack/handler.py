from abc import ABC, abstractmethod
from typing import Any, Set

from qcir import Circuit, Instruction

from .instruction_definition import InstructionDefinition


class Handler(ABC):
    @property
    @abstractmethod
    def source(self) -> InstructionDefinition:
        pass

    @property
    @abstractmethod
    def uses(self) -> Set[InstructionDefinition]:
        pass

    @abstractmethod
    def handle(self, instruction: Instruction, context: Any) -> Circuit:
        pass
