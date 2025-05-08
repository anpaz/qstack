from qstack.gadget_definition import GadgetDefinition
import compilers.passes

from qstack.circuit import Circuit, Instruction
from qstack.gadget import QuantumKernel

import qstack.layers.apps.gadgets as apps
import qstack.layers.matrix.instruction_set as matrix

from . import handlers

source_instruction_set = {
    getattr(apps, instr) for instr in dir(apps) if isinstance(getattr(apps, instr), GadgetDefinition)
}

target_instruction_set = [
    getattr(matrix, instr) for instr in dir(matrix) if isinstance(getattr(matrix, instr), GadgetDefinition)
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


def compile(kernel: QuantumKernel) -> QuantumKernel:
    def decoder(memory: list[bool]) -> int:
        return kernel.decoder(memory)

    # Make sure the circuit in the kernel uses the right instruction set:
    compilers.passes.verify_instructions(kernel.circuit, source_instruction_set)

    target_circuit = Circuit(kernel.name, [])

    for inst in [inst for inst in kernel.circuit.instructions if isinstance(inst, Instruction)]:
        handler = handlers[inst.name]
        target_circuit += handler(inst)

    target_instructions = compilers.passes.verify_instructions(target_circuit, target_instruction_set)

    return QuantumKernel(
        name=kernel.name,
        circuit=target_circuit,
        instruction_set=target_instructions,
        decoder=decoder,
    )
