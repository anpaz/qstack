from dataclasses import dataclass, replace
from typing import Any, Callable

from .processors import CPU, Outcome
from .ast import ClassicInstruction, Kernel, ParameterValue


class ClassicalContext:
    def __init__(self):
        self.measurements = []

    def collect(self, result: Outcome):
        self.measurements.append(result)

    def consume(self) -> Outcome:
        if len(self.measurements) > 0:
            return self.measurements.pop()


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


class ClassicProcessor(CPU):
    def __init__(self, instructions: set[ClassicDefinition]):
        self.operations = {inst.name.lower(): inst for inst in instructions}

    def restart(self):
        self.context = ClassicalContext()

    def collect(self, result: Outcome):
        self.context.collect(result)

    def consume(self) -> Outcome:
        return self.context.consume()

    def eval(self, instruction: ClassicInstruction) -> Kernel:
        name = instruction.name.lower()
        assert name in self.operations, f"Invalid classic instruction {instruction.name}."
        info = self.operations[name]
        parameters = {name: instruction.parameters[name] for name in info.parameters}

        result = info.callback(self.context, **parameters)

        if isinstance(result, Kernel):
            return result
        elif result is None:
            return Kernel.empty()
        else:
            raise ValueError(f"Invalid result {result}")


# def from_layer(layer: Layer) -> ClassicProcessor:
#     return ClassicProcessor(instructions=layer.classic_definitions)


# def _add_compilation(instr: ClassicDefinition, node: LayerNode):
#     compiler = node.lower.compiler
#     callback = instr.callback

#     def call_and_compile(*targets, **parameters):
#         result = callback(*targets, **parameters)
#         if isinstance(result, Kernel):
#             new_kernel = compiler.eval(result, node)
#             return new_kernel
#         else:
#             return result

#     return replace(instr, callback=call_and_compile)


# def _find_all_instructions(node: LayerNode):
#     if node.lower is not None:
#         for instr in _find_all_instructions(node.lower.lower):
#             yield _add_compilation(instr, node)

#     for instr in node.layer.classic_definitions:
#         yield replace(instr, name=f"{node.namespace}{instr.name}")


def from_callbacks(callbacks: set[ClassicDefinition] | None) -> ClassicProcessor:
    return ClassicProcessor(instructions=callbacks or set())
