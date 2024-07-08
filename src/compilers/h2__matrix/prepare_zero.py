from instruction_sets.h2 import instructions as h2
from instruction_sets.matrix import instructions as matrix
from qcir.circuit import Circuit, Comment, Instruction
from qstack import Handler, InstructionDefinition


class PrepareZero(Handler):
    @property
    def source(self):
        return h2.PrepareZero

    def uses(self) -> set[InstructionDefinition]:
        return {}

    def handle(self, inst: Instruction, _):
        return None
