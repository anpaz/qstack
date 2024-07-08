import cmath

from instruction_sets.h2 import instructions as h2
from instruction_sets.matrix import instructions as matrix
from qcir.circuit import Circuit, Comment, Instruction
from qstack import Handler, InstructionDefinition


class ZZ(Handler):
    @property
    def source(self):
        return h2.ZZ

    def uses(self) -> set[InstructionDefinition]:
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
                Comment(f"start: " + inst.name), 
                matrix.Matrix2(parameters=m, targets=inst.targets)],
        )
        # fmt: on
