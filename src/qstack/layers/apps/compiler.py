import qstack.compilers.passes

from qstack.circuit import Circuit
from qstack.gadget_definition import GadgetDefinition
from qstack.gadget import Gadget

from . import instruction_set

known_instructions = {
    getattr(instruction_set, instr)
    for instr in dir(instruction_set)
    if isinstance(getattr(instruction_set, instr), GadgetDefinition)
}


def compile(circuit: Circuit, *, name: str) -> Gadget:
    qstack.compilers.passes.verify_instructions(circuit, known_instructions)

    return Gadget(name=name, circuit=circuit)
