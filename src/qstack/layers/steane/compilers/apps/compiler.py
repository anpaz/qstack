from qstack.instruction_definition import InstructionDefinition
import qstack.compilers.passes

from qcir.circuit import Circuit, Instruction, QubitId, RegisterId
import qstack.paulis
from qstack.gadget import Gadget

import qstack.layers.apps.instruction_set as apps
import qstack.layers.stabilizer.instruction_set as st

from . import gadgets
from . import decompose

import logging

logger = logging.getLogger("qstack")


source_instruction_set = {
    getattr(apps, instr) for instr in dir(apps) if isinstance(getattr(apps, instr), InstructionDefinition)
}


def compile(gadget: Gadget) -> Gadget:

    circuit = decompose.run(gadget.circuit)
    logger.debug("Decomposed circuit: %s", circuit)

    handlers = {
        name: handler
        for (gate, handler) in [
            (st.PrepareZero, gadgets.prepare_zero),
            (st.H, gadgets.h),
            (st.X, gadgets.x),
            (st.CX, gadgets.cx),
            (st.MeasureZ, gadgets.measure_z),
        ]
        for name in [gate.name] + list(gate.aliases or [])
    }

    qubit_count = circuit.qubit_count
    register_count = circuit.register_count

    compiled_gadgets: list[Gadget] = []
    context = gadgets.Context(qubit_count=qubit_count, register_count=register_count)

    for inst in [inst for inst in circuit.instructions if isinstance(inst, Instruction)]:
        handler = handlers[inst.name]
        compiled_gadgets.append(handler(inst, context))

    new_circuit = Circuit([])
    for g in compiled_gadgets:
        new_circuit += g.circuit

    logger.debug("Encoded circuit: %s", new_circuit)

    def steane_code_decoder(memory: tuple[bool]) -> int:
        memory = list(memory)
        correction = [qstack.paulis.I] * context.qubit_count
        for g in compiled_gadgets:
            g.decoder(memory, correction)

        if gadget.decoder:
            return gadget.decoder(tuple(memory[:register_count]))
        else:
            return tuple(memory[:register_count])

    return Gadget(gadget.name, new_circuit, decoder=steane_code_decoder)
