from qcir.circuit import Circuit, Instruction, QubitId, RegisterId
from qstack import InstructionDefinition
from qstack.handler import Translator

from .. import standard
from .. import matrix


class MeasureZ(Translator):
    @property
    def supports(self) -> InstructionDefinition:
        return standard.MeasureZ

    def compile(self, source: Instruction) -> Circuit:
        return Circuit(
            self.__qualname__,
            matrix.InstructionSet.name,
            [matrix.Measure(targets=source.targets)],
        )
