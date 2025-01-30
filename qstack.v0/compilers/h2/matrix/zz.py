import cmath

from runtimes.h2 import instruction_set as instruction_set
from runtimes.matrix.instruction_set import instructions as matrix
from qstack.circuit import Circuit, Comment, Instruction
from qstack import Handler, GadgetDefinition


class ZZ(Handler):
    @property
    def source(self):
        return instruction_set.ZZ

    def uses(self) -> set[GadgetDefinition]:
        return {
            matrix.Matrix2,
        }

    def handle(self, inst: Instruction, _):
        i = 1j
        const = cmath.exp(-i * cmath.pi / 4.0)
        # fmt: off
        m = [
            const,       0,       0,     0,
                0, i*const,       0,     0,
                0,       0, i*const,     0,
                0,       0,       0, const,
        ]
        return Circuit(
            self.__class__.__name__,
            [
                Comment("start: " + inst.name), 
                matrix.Matrix2(parameters=m, targets=inst.targets)],
        )
        # fmt: on
