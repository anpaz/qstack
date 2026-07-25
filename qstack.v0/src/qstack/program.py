from dataclasses import dataclass
from .ast import Kernel
from .instruction_set import InstructionSet


@dataclass(frozen=True)
class Program:
    instruction_set: InstructionSet
    kernels: tuple[Kernel]

    @property
    def depth(self):
        return max(k.depth for k in self.kernels)

    def __str__(self):
        attributes = ["@instruction-set: " + str(self.instruction_set)]
        kernels = [str(k) for k in self.kernels]

        return "\n".join(attributes + [""] + kernels)

    @staticmethod
    def from_string(program: str, instruction_set=None) -> "Program":
        from qstack.parser import QStackParser

        parser = QStackParser(instruction_set=instruction_set)
        program = parser.parse(program)
        return program
