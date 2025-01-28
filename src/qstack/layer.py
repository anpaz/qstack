from dataclasses import dataclass
from typing import Callable, Set, Type

from .ast import ContinuationKernel, DecoderKernel, QubitId, Instruction, ParameterValue, Outcome, Kernel

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
class InstructionDefinition:
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

        return Instruction(name=self.name, targets=qubit_ids, parameters=parameters)

    def action(self, **parameters: ParameterValue) -> Matrix:
        if len(self.parameters) == 0:
            assert self.matrix is not None, f"Instruction {self.name} has no matix nor parameters defined"
            return self.matrix
        assert False, f"Instruction {self.name} accepts parameters. It must implement the `action` method."

    def __hash__(self):
        return hash(self.name)


@dataclass(frozen=True)
class ContinuationDefinition:
    name: str
    callback: Callable[[list[Outcome]], Kernel] | None
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

        return ContinuationKernel(name=self.name, parameters=parameters)

    def action(self, **parameters: ParameterValue) -> Callable[[list[Outcome]], Kernel]:
        if len(self.parameters) == 0:
            assert self.callback is not None, f"Continuation {self.name} has no callback nor parameters defined"
            return self.matrix
        assert False, f"Instruction {self.name} accepts parameters. It must implement the `action` method."


@dataclass(frozen=True)
class DecoderDefinition:
    name: str
    callback: Callable[[list[Outcome]], Outcome] | None
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

        return DecoderKernel(name=self.name, parameters=parameters)

    def action(self, **parameters: ParameterValue) -> Callable[[list[Outcome]], Kernel]:
        if len(self.parameters) == 0:
            assert self.callback is not None, f"Continuation {self.name} has no callback nor parameters defined"
            return self.matrix
        assert False, f"Decoder {self.name} accepts parameters. It must implement the `action` method."


@dataclass(frozen=True)
class Layer:
    name: str
    instructions: Set[InstructionDefinition]
    decoders: Set[DecoderDefinition]
    continuations: Set[ContinuationDefinition]
