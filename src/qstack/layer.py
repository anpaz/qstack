from dataclasses import dataclass
from typing import Callable, Set, Type

from .ast import (
    ClassicInstruction,
    QubitId,
    QuantumInstruction,
    ParameterValue,
    Outcome,
    Kernel,
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
class ClassicDefinition:
    name: str
    parameters: tuple[str]
    callback: Callable[[tuple[Outcome]], Kernel]

    def __call__(
        self,
        **parameters: ParameterValue,
    ):
        # TODO: check_types(parameters, self.parameters)

        return ClassicInstruction(name=self.name, parameters=parameters)

    @staticmethod
    def from_callback(callback: Callable[[tuple[Outcome]], Kernel]):
        import inspect

        signature = inspect.signature(callback)
        parameters_names = tuple(
            [p.name for p in signature.parameters.values() if p.kind == inspect.Parameter.KEYWORD_ONLY]
        )

        return ClassicDefinition(name=callback.__name__, callback=callback, parameters=parameters_names)


@dataclass(frozen=True)
class Layer:
    name: str
    quantum_definitions: Set[QuantumDefinition]
    classic_definitions: Set[ClassicDefinition]

    def extend_with(
        self,
        classic: Set[ClassicDefinition] | None = None,
        quantum: Set[QuantumDefinition] | None = None,
    ):
        return Layer(
            name=f"{self.name}.extended",
            quantum_definitions=self.quantum_definitions.union(quantum or set()),
            classic_definitions=self.classic_definitions.union(classic or set()),
        )
