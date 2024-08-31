from runtimes.h2 import instruction_set as instruction_set
from qcir.circuit import Instruction
from qstack import Handler, InstructionDefinition


class PrepareZero(Handler):
    @property
    def source(self):
        return instruction_set.PrepareZero

    def uses(self) -> set[InstructionDefinition]:
        return {}

    def handle(self, inst: Instruction, _):
        return None
