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
class ParameterDefinition:
    name: str
    type: Type
    required: bool = True
    default: ParameterValue | None = None


@dataclass(frozen=True)
class TargetDefinition(ParameterDefinition):
    def __init__(self, name: str, required: bool = True):
        super().__init__(name=name, required=required, type=QubitId)


@dataclass(frozen=True)
class QuantumInstructionDefinition:
    name: str
    targets: tuple[TargetDefinition]
    matrix: Matrix | None
    parameters: tuple[ParameterDefinition] = tuple()

    def __call__(
        self,
        *targets: str | QubitId,
        **parameters: ParameterValue,
    ):
        qubit_ids = [QubitId.wrap(q) for q in targets]
        # check_types(targets, self.targets)

        if parameters:
            assert self.parameters, f"Instruction {self.name} is not expecting parameters."
            # check_types(parameters, self.parameters)
        else:
            assert not self.parameters

        return QuantumInstruction(name=self.name, targets=qubit_ids, parameters=parameters)

    def action(self, **parameters: ParameterValue) -> Matrix:
        if len(self.parameters) == 0:
            assert self.matrix is not None, f"Instruction {self.name} has no matix nor parameters defined"
            return self.matrix
        assert False, f"Instruction {self.name} accepts parameters. It must implement the `action` method."

    def __hash__(self):
        return hash(self.name)


@dataclass(frozen=True)
class ClassicInstructionDefinition:
    name: str
    callback: Callable[[list[Outcome]], Kernel]
    parameters: tuple[ParameterDefinition] = tuple()

    def __call__(
        self,
        **parameters: ParameterValue,
    ):
        # check_types(targets, self.targets)

        if parameters:
            assert self.parameters, f"Instruction {self.name} is not expecting parameters."
            # check_types(parameters, self.parameters)
        else:
            assert not self.parameters

        return ClassicInstruction(
            name=self.name, callback=f"{self.callback.__module__}.{self.callback.__qualname__}", parameters=parameters
        )


@dataclass(frozen=True)
class Layer:
    name: str
    quantum_instructions: Set[QuantumInstructionDefinition]
    classic_instructions: Set[ClassicInstructionDefinition]
