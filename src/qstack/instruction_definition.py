from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class InstructionType:
    MEASUREMENT = "measurement"
    PREPARATION = "prepare"
    UNITARY = "unitary"


class InstructionDefinition(ABC):
    @property
    @abstractmethod
    def names(self) -> list[str]:
        pass

    @property
    @abstractmethod
    def matrix(self) -> np.ndarray | None:
        pass

    # @property
    # def instruction_type() -> str:
    #     return InstructionType.UNITARY
