from runtimes.h2 import instruction_set as instruction_set
from qstack.circuit import Instruction
from qstack import Handler, GadgetDefinition


class PrepareZero(Handler):
    @property
    def source(self):
        return instruction_set.PrepareZero

    def uses(self) -> set[GadgetDefinition]:
        return {}

    def handle(self, inst: Instruction, _):
        return None
