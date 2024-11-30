import qstack.compilers.passes

from qstack.circuit import Circuit
from qstack.gadget_definition import GadgetDefinition
from qstack.gadget import QuantumKernel

from . import instruction_set

known_instructions = {
    getattr(instruction_set, instr)
    for instr in dir(instruction_set)
    if isinstance(getattr(instruction_set, instr), GadgetDefinition)
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
