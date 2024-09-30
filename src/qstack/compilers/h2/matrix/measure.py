from runtimes.h2 import instruction_set as instruction_set
from runtimes.matrix.instruction_set import instructions as matrix
from qcir.circuit import Circuit, Instruction
from qstack import Handler, InstructionDefinition


class Measure(Handler):
    @property
    def source(self):
        return instruction_set.Measure

    def uses(self) -> set[InstructionDefinition]:
        return {
            matrix.Measure,
        }

    def handle(self, inst: Instruction, _):
        return Circuit(
            self.__class__.__name__,
            [
                matrix.Measure(targets=inst.targets),
            ],
        )
