from qstack.instruction_definition import InstructionDefinition
import qstack.compilers.passes

from qcir.circuit import Circuit, Instruction
from qstack.gadget import Gadget

import qstack.layers.apps.instruction_set as apps
import qstack.layers.cliffords.instruction_set as clifford

from . import handlers

source_instruction_set = {
    getattr(apps, instr) for instr in dir(apps) if isinstance(getattr(apps, instr), InstructionDefinition)
}

target_instruction_set = [
    getattr(clifford, instr) for instr in dir(clifford) if isinstance(getattr(clifford, instr), InstructionDefinition)
]


handlers = {
    name: handler
    for (gate, handler) in [
        (apps.Measure, handlers.handle_measure),
        (apps.PrepareOne, handlers.handle_prepare_one),
        (apps.PrepareZero, handlers.handle_prepare_zero),
        (apps.PrepareRandom, handlers.handle_prepare_random),
        (apps.PrepareBell, handlers.handle_prepare_bell),
    ]
    for name in [gate.name] + list(gate.aliases or [])
}


def compile(gadget: Gadget) -> Gadget:
    # Make sure the circuit in the kernel uses the right instruction set:
    qstack.compilers.passes.verify_instructions(gadget.circuit, source_instruction_set)

    target_circuit = Circuit([])

    for inst in [inst for inst in gadget.circuit.instructions if isinstance(inst, Instruction)]:
        handler = handlers[inst.name]
        target_circuit += handler(inst)

    qstack.compilers.passes.verify_instructions(target_circuit, target_instruction_set)

    return Gadget(name=gadget.name, circuit=target_circuit)
