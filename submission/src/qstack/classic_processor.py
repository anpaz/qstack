from dataclasses import dataclass, replace
from typing import Any, Callable

from .processors import CPU, Outcome
from .ast import ClassicInstruction, Kernel, ParameterValue


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
    def from_callback(callback: Callable[[Any], Kernel]):
        import inspect

        signature = inspect.signature(callback)
        parameters_names = tuple(
            [p.name for p in signature.parameters.values() if p.kind == inspect.Parameter.KEYWORD_ONLY]
        )

        return ClassicDefinition(name=callback.__name__, callback=callback, parameters=parameters_names)


class ClassicContext:
    def __init__(self):
        self.measurements = []

    def collect(self, result: Outcome):
        self.measurements.append(result)

    def consume(self) -> Outcome:
        if len(self.measurements) > 0:
            return self.measurements.pop()

    def __str__(self):
        return str(self.measurements)

    def __iter__(self):
        return iter(self.measurements)


class ClassicProcessor(CPU):
    def __init__(self, instructions: set[ClassicDefinition]):
        self.operations = {inst.name.lower(): inst for inst in instructions}
        self._context = ClassicContext()

    def restart(self):
        self._context = ClassicContext()

    @property
    def context(self) -> ClassicContext:
        return self._context

    def eval(self, instruction: ClassicInstruction | None, outcome: Outcome | None) -> Kernel | None:
        if outcome is not None:
            self.context.collect(outcome)

        if instruction is None:
            return None

        name = instruction.name.lower()
        assert name in self.operations, f"Invalid classic instruction {instruction.name}."
        info = self.operations[name]
        parameters = {name: instruction.parameters[name] for name in info.parameters}

        result = info.callback(self.context, **parameters)

        if isinstance(result, Kernel):
            return result
        elif result is None:
            return None
        else:
            raise ValueError(f"Invalid result {result}")


def from_callbacks(callbacks: set[ClassicDefinition] | None) -> ClassicProcessor:
    return ClassicProcessor(instructions=callbacks or set())
