from qstack.instruction_definition import InstructionDefinition
import qstack.compilers.passes

from qcir.circuit import Circuit, Instruction
from qstack.quantum_kernel import QuantumKernel

import qstack.layers.apps.instruction_set as apps
import qstack.layers.cliffords.instruction_set as clifford

from . import decompose

source_instruction_set = {
    getattr(apps, instr) for instr in dir(apps) if isinstance(getattr(apps, instr), InstructionDefinition)
}

target_instruction_set = [
    getattr(clifford, instr) for instr in dir(clifford) if isinstance(getattr(clifford, instr), InstructionDefinition)
]
