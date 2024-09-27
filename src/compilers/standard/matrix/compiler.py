from qstack.instruction_definition import InstructionDefinition
import compilers.passes

from qcir.circuit import Circuit, Instruction
from qstack.quantum_kernel import QuantumKernel

import runtimes.standard.instruction_set as standard
import runtimes.matrix.instruction_set as matrix

from . import handlers

source_instruction_set = [
    getattr(standard, instr) for instr in dir(standard) if isinstance(getattr(standard, instr), InstructionDefinition)
]

target_instruction_set = [
    getattr(matrix, instr) for instr in dir(matrix) if isinstance(getattr(matrix, instr), InstructionDefinition)
]


handlers = {
    name: handler
    for (gate, handler) in [
        (standard.MeasureZ, handlers.handle_mz),
        (standard.PrepareBell, handlers.handle_prepare_bell),
        (standard.PrepareZero, handlers.handle_prepare_zero),
        (standard.Hadamard, handlers.handle_hadamard),
        (standard.CtrlX, handlers.handle_ctrlx),
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
