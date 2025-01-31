from dataclasses import dataclass
import inspect
from typing import Callable

from .processors import CPU, Outcome
from .ast import ClassicInstruction, Kernel
from .layer import Layer, ClassicDefinition


@dataclass(frozen=True)
class CallbackInfo:
    callback: Callable
    outcomes_length: int
    parameters: tuple[str]

    @staticmethod
    def from_callable(func: Callable):
        signature = inspect.signature(func)
        outcomes_length = len(
            [p for p in signature.parameters.values() if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD]
        )
        parameters_names = [p.name for p in signature.parameters.values() if p.kind == inspect.Parameter.KEYWORD_ONLY]

        return CallbackInfo(callback=func, outcomes_length=outcomes_length, parameters=parameters_names)


class ClassicProcessor(CPU):
    def __init__(self, instructions: set[ClassicDefinition]):
        self.operations = {inst.name.lower(): CallbackInfo.from_callable(inst.callback) for inst in instructions}

    def restart(self):
        self.measurements = []

    def collect(self, result: Outcome):
        self.measurements.append(result)

    def consume(self) -> Outcome:
        if len(self.measurements) > 0:
            return self.measurements.pop()

    def eval(self, instruction: ClassicInstruction) -> Kernel:
        name = instruction.name.lower()
        assert name in self.operations, f"Invalid classic instruction {instruction.name}."
        info = self.operations[name]

        targets = [self.consume() for _ in range(info.outcomes_length)]
        parameters = {name: instruction.parameters[name] for name in info.parameters}

        result = info.callback(*targets, **parameters)

        if isinstance(result, Kernel):
            return result
        elif isinstance(result, int):
            self.collect(result)
            return Kernel.empty()
        elif result is None:
            return Kernel.empty()
        else:
            raise ValueError(f"Invalid result {result}")


def from_layer(layer: Layer) -> ClassicProcessor:
    return ClassicProcessor(instructions=layer.classic_definitions)
