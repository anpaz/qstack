
from qstack.instruction_definition import InstructionDefinition


class MeasureZ(InstructionDefinition):
    @property
    def names(self):
        return ["⟨+z|", "mz"]

    # @property
    # def instruction_type(self) -> str:
    #     return InstructionType.MEASUREMENT

    def matrix(self):
        return None
