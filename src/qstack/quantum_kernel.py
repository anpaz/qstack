from dataclasses import dataclass
from typing import Callable, Set

from qcir.circuit import Circuit
from .instruction_definition import InstructionDefinition


@dataclass(frozen=True)
class QuantumKernel:
    name: str

    instruction_set: Set[InstructionDefinition]

    circuit: Circuit
    decoder: Callable[[list[bool]], list[bool] | None]

    @property
    def qubit_count(self) -> int:
        return self.circuit.qubit_count

    @property
    def register_count(self) -> int:
        return self.circuit.register_count
