import qstack.compilers.passes

from qcir.circuit import Circuit
from qstack.instruction_definition import InstructionDefinition
from qstack.gadget import Gadget

from . import instruction_set

known_instructions = {
    getattr(instruction_set, instr)
    for instr in dir(instruction_set)
    if isinstance(getattr(instruction_set, instr), InstructionDefinition)
}


def compile(circuit: Circuit, *, name: str) -> Gadget:
    qstack.compilers.passes.verify_instructions(circuit, known_instructions)

    return Gadget(name=name, circuit=circuit)
