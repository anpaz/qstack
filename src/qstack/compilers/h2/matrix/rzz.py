import cmath

from runtimes.h2 import instruction_set as instruction_set
from runtimes.matrix.instruction_set import instructions as matrix
from qstack.circuit import Circuit, Comment, Instruction
from qstack import Handler, GadgetDefinition


class RZZ(Handler):
    @property
    def source(self):
        return instruction_set.RZZ

    def uses(self) -> set[GadgetDefinition]:
        return {
            matrix.Matrix2,
        }

    def handle(self, inst: Instruction, _):
        theta = inst.parameters[0]
        i = 1j
        const = cmath.exp(-i * theta / 2.0)
        a = cmath.exp(i * theta)
        # fmt: off
        m = [
            const,     0.0,      0.0,   0.0,
               0.0, a*const,     0.0,   0.0,
               0.0,     0.0, a*const,    0.0,
               0.0,     0.0,     0.0, const,
        ]
        return Circuit(
            self.__class__.__name__,
            [
                Comment("start: " + inst.name), 
                matrix.Matrix2(parameters=m, targets=inst.targets)],
        )
        # fmt: on
