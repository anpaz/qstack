from dataclasses import dataclass, replace
import inspect
from typing import Callable

from .processors import CPU, Outcome
from .ast import ClassicInstruction, Kernel
from .layer import Layer, ClassicDefinition
from .stack import Stack, LayerNode, CompilerNode
from .program import Program
from .compiler import Compiler


class ClassicProcessor(CPU):
    def __init__(self, instructions: set[ClassicDefinition]):
        self.operations = {inst.name.lower(): inst for inst in instructions}

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


def _add_compilation(instr: ClassicDefinition, node: LayerNode):
    compiler = node.lower.compiler
    callback = instr.callback

    def call_and_compile(*targets, **parameters):
        result = callback(*targets, **parameters)
        if isinstance(result, Kernel):
            new_kernel = compiler.eval(result, node)
            return new_kernel
        else:
            return result

    return replace(instr, callback=call_and_compile)


def _find_all_instructions(node: LayerNode):
    if node.lower is not None:
        for instr in _find_all_instructions(node.lower.lower):
            yield _add_compilation(instr, node)

    for instr in node.layer.classic_definitions:
        yield replace(instr, name=f"{node.namespace}{instr.name}")


def from_stack(stack: Stack) -> ClassicProcessor:
    instructions = set(_find_all_instructions(stack.target))
    return ClassicProcessor(instructions=instructions)
