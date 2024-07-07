from dataclasses import dataclass
from .instruction_definition import InstructionDefinition
from .compiler import Compiler



@dataclass(frozen=True)
class Stack:
    instruction_set: set[InstructionDefinition]
    emulator: emulators.Emulator | None = None
    compiler: "Stack" | None = None

stacks = {}
def init(config):
    for i in config:
        stacks[i] = config[i]



def create_stack(target: str):
    if target == "standard":
        return Stack(standard.InstructionSet)

    elif target == "matrix":
        return Stack(matrix.InstructionSet, emulator=emulators.MatrixEmulator)

    elif target == "standard.matrix":
        return Stack(standard.InstructionSet, compiler=Compiler(standard.InstructionSet, matrix.InstructionSet, [
            standard__matrix.
        ]))

    else:
        assert False, f"Invalid instruction set: {target}"
