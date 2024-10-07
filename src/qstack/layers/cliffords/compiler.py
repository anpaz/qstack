import qstack.compilers.passes

from qcir.circuit import Circuit
from qstack.instruction_definition import InstructionDefinition
from qstack.gadget import QuantumKernel

from . import instruction_set

known_instructions = {
    getattr(instruction_set, instr)
    for instr in dir(instruction_set)
    if isinstance(getattr(instruction_set, instr), InstructionDefinition)
}


def compile(circuit: Circuit) -> QuantumKernel:
    def no_decoder(memory: list[bool]):
        return memory

    instructions = qstack.compilers.passes.verify_instructions(circuit, known_instructions)

    return QuantumKernel(
        name=circuit.name,
        circuit=circuit,
        instruction_set=instructions,
        decoder=no_decoder,
    )
