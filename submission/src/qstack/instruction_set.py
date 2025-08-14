from dataclasses import dataclass
from typing import Callable, Set

from .ast import (
    QubitId,
    QuantumInstruction,
    ParameterValue,
)

type Matrix = tuple[tuple]


@dataclass(frozen=True)
class QuantumDefinition:
    name: str
    targets_length: int
    matrix: Matrix | None
    factory: Callable[[list[ParameterValue]], Matrix] | None = None

    def __call__(
        self,
        *targets: str | QubitId,
        **parameters: ParameterValue,
    ):
        # TODO: check_types(targets, self.targets)

        qubit_ids = [QubitId.wrap(q) for q in targets]
        return QuantumInstruction(name=self.name, targets=qubit_ids, parameters=parameters)

    @staticmethod
    def from_matrix(name: str, targets: int, matrix: Matrix):
        return QuantumDefinition(name=name, targets_length=targets, matrix=matrix, factory=None)

    @staticmethod
    def with_parameters(name: str, targets: int, factory: Callable[[list[ParameterValue]], Matrix]):
        return QuantumDefinition(name=factory.__name__, targets_length=targets, matrix=None, factory=factory)

    def __hash__(self):
        return hash(self.name)


@dataclass(frozen=True)
class InstructionSet:
    name: str
    quantum_definitions: Set[QuantumDefinition]

    def extend_with(
        self,
        quantum: Set[QuantumDefinition],
    ):
        return InstructionSet(
            name=f"{self.name}.extended", quantum_definitions=self.quantum_definitions.union(quantum)
        )

    def __str__(self):
        return str(self.name)
