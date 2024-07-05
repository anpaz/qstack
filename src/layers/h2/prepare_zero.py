
from qstack.instruction_definition import InstructionDefinition


class PrepareZero(InstructionDefinition):
    @property
    def names(self):
        return ["|0>", "|0⟩", "prepare_zero"]

    # @property
    # def instruction_type(self) -> str:
    #     return InstructionType.PREPARATION

    def matrix(self):
        return None
