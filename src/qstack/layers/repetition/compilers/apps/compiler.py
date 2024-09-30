from qstack.instruction_definition import InstructionDefinition
import qstack.compilers.passes

from qcir.circuit import Circuit, Instruction, QubitId
from qstack.quantum_kernel import QuantumKernel

import qstack.layers.apps.instruction_set as apps
import qstack.layers.stabilizer.instruction_set as st

from . import encoders
from . import decompose

source_instruction_set = {
    getattr(apps, instr) for instr in dir(apps) if isinstance(getattr(apps, instr), InstructionDefinition)
}


def compile(kernel: QuantumKernel) -> QuantumKernel:

    circuit = decompose.run(kernel.circuit)

    handlers = {
        name: handler
        for (gate, handler) in [
            (st.PrepareZero, encoders.encode_prepare_zero),
            (st.H, encoders.encode_h),
            (st.X, encoders.encode_x),
            (st.CX, encoders.encode_cx),
            (st.MeasureZ, encoders.encode_measure),
        ]
        for name in [gate.name] + list(gate.aliases or [])
    }

    target_circuit = Circuit(kernel.name, [])
    context = encoders.Context(
        kernel,
        stabilizer=[
            ["Z", "Z", "I"],
            ["Z", "I", "Z"],
        ],
        x_op=["X", "X", "X"],
        z_op=["Z", "I", "I"],
    )

    for inst in [inst for inst in circuit.instructions if isinstance(inst, Instruction)]:
        handler = handlers[inst.name]
        target_circuit += handler(inst, context)

    # target_instructions = qstack.compilers.passes.verify_instructions(target_circuit, target_instruction_set)

    def decoder(memory: tuple[bool]) -> int:
        memory = list(memory)
        correction = {QubitId(i): ["I", "I", "I"] for i in range(kernel.qubit_count)}
        for decoder in context.decoders:
            decoder(memory, correction)
        return tuple(memory[: kernel.register_count])

    return QuantumKernel(
        name=kernel.name,
        circuit=target_circuit,
        instruction_set=set(),
        decoder=decoder,
    )
