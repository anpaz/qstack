import cmath

from instruction_sets.h2 import instructions as h2
from instruction_sets.matrix import instructions as matrix
from qcir.circuit import Circuit, Comment, Instruction
from qstack import Handler, InstructionDefinition


class RZZ(Handler):
    @property
    def source(self):
        return h2.RZZ

    def uses(self) -> set[InstructionDefinition]:
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
                Comment(f"start: " + inst.name), 
                matrix.Matrix2(parameters=m, targets=inst.targets)],
        )
        # fmt: on
