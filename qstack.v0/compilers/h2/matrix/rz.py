import cmath

from runtimes.h2 import instruction_set as instruction_set
from runtimes.matrix.instruction_set import instructions as matrix
from qstack.circuit import Circuit, Comment, Instruction
from qstack import Handler, GadgetDefinition


class RZ(Handler):
    @property
    def source(self):
        return instruction_set.RZ

    def uses(self) -> set[GadgetDefinition]:
        return {
            matrix.Matrix1,
        }

    def handle(self, inst: Instruction, _):
        i = 1j
        theta = inst.parameters[0]
        a_00 = cmath.exp(-i * theta / 2.0)
        a_11 = cmath.exp(i * theta / 2.0)
        # fmt: off
        m = [
            a_00, 0.0,
            0.0, a_11,
        ]
        return Circuit(
            self.__class__.__name__,
            [
                Comment("start: " + inst.name), 
                matrix.Matrix1(parameters=m, targets=inst.targets)],
        )
        # fmt: on
