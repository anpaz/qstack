from .instruction_definition import InstructionDefinition


class QVM:
    def __init__(self, instruction_set: set[InstructionDefinition]):
        self._instructions = instruction_set

    def create_emulator(self):
        from .emulators.pyquil import pyQuilEmulator

        return pyQuilEmulator(self._instructions)


def create_qvm(target: str):
    if target == "standard":
        from layers.standard import StandardInstructionSet

        return QVM(StandardInstructionSet.instruction_set)
