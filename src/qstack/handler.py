from abc import ABC, abstractmethod
from typing import Any, Set

from qcir import Circuit, Instruction

from .gadget_definition import GadgetDefinition


class Handler(ABC):
    @property
    @abstractmethod
    def source(self) -> GadgetDefinition:
        pass

    @property
    @abstractmethod
    def uses(self) -> Set[GadgetDefinition]:
        pass

    @abstractmethod
    def handle(self, instruction: Instruction, context: Any) -> Circuit:
        pass
