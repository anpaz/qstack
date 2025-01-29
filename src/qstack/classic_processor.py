from .processors import CPU, Outcome
from .ast import ClassicInstruction, Kernel
from .layer import Layer


class ClassicProcessor(CPU):
    def __init__(self, instructions: set[ClassicInstruction]):
        self.operations = instructions

    def restart(self):
        self.measurements = []

    def collect(self, result: Outcome):
        self.measurements.append(result)

    def consume(self) -> Outcome:
        if len(self.measurements) > 0:
            return self.measurements.pop()

    def eval(self, instruction: ClassicInstruction) -> Kernel:
        return Kernel.empty()


def from_layer(layer: Layer) -> ClassicProcessor:
    return ClassicProcessor(instructions=layer.classic_instructions)
