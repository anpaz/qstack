from .instruction_definition import InstructionDefinition

from layers.h2 import H2InstructionSet
from layers.standard import StandardInstructionSet


class Stack:
    def __init__(self, instruction_set: set[InstructionDefinition]):
        self._instructions = instruction_set

    def create_emulator(self):
        from .emulators.pyquil import pyQuilEmulator

        return pyQuilEmulator(self._instructions)


def create_stack(target: str):
    if target == "standard":
        return Stack(StandardInstructionSet.instruction_set)

    elif target == "h2":
        return Stack(H2InstructionSet.instruction_set)

    else:
        assert False, f"Invalid instruction set: {target}"
