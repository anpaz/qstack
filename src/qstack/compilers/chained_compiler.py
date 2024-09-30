from typing import Sequence

from qcir.circuit import Circuit
from qstack import InstructionDefinition

from .base_compiler import BaseCompiler


class ChainedCompiler:
    def __init__(self, workers: Sequence[BaseCompiler]):
        self.workers = tuple(workers)
        assert len(self.workers) > 0

    @property
    def input_instruction_set(self) -> set[InstructionDefinition]:
        return self.workers[0].input_instruction_set

    @property
    def output_instruction_set(self) -> set[InstructionDefinition]:
        return self.workers[-1].output_instruction_set

    def compile(self, source: Circuit) -> Circuit:
        target = source
        for compiler in self.workers:
            target = compiler.compile(target)
        return target
