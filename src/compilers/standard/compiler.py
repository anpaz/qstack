import runtimes.standard.instruction_set as standard
import compilers.passes

from qcir.circuit import Circuit
from qstack.instruction_definition import InstructionDefinition
from qstack.quantum_kernel import QuantumKernel


known_instructions = [
    getattr(standard, instr) for instr in dir(standard) if isinstance(getattr(standard, instr), InstructionDefinition)
]


def compile(circuit: Circuit) -> QuantumKernel:
    def no_decoder(memory: list[bool]):
        return memory

    instructions = compilers.passes.verify_instructions(circuit, known_instructions)

    return QuantumKernel(
        name=circuit.name,
        circuit=circuit,
        instruction_set=instructions,
        decoder=no_decoder,
    )
