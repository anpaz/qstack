import numpy as np

from qstack.instruction_definition import InstructionDefinition, InstructionType


class MeasureZ(InstructionDefinition):
    @property
    def names(self):
        return ["⟨+z|", "mz"]

    # @property
    # def instruction_type(self) -> str:
    #     return InstructionType.MEASUREMENT

    @property
    def matrix(self):
        return None