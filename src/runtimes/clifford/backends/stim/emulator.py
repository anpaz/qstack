from typing import Iterable

from qcir.circuit import Circuit, Instruction
from qstack.instruction_definition import InstructionDefinition

from .context import Context
from . import handlers

import logging
import runtimes.clifford.instruction_set as clifford

logger = logging.getLogger("qstack")


handlers = {
    name: handler
    for (gate, handler) in [
        (clifford.PrepareZero, handlers.handle_prepare),
        (clifford.H, handlers.handle_1qubit),
        (clifford.X, handlers.handle_1qubit),
        (clifford.Y, handlers.handle_1qubit),
        (clifford.Z, handlers.handle_1qubit),
        (clifford.S, handlers.handle_1qubit),
        (clifford.SX, handlers.handle_1qubit),
        (clifford.SY, handlers.handle_1qubit),
        (clifford.SAdj, handlers.handle_1qubit),
        (clifford.SXAdj, handlers.handle_1qubit),
        (clifford.SYAdj, handlers.handle_1qubit),
        (clifford.CX, handlers.handle_2qubit),
        (clifford.CY, handlers.handle_2qubit),
        (clifford.CZ, handlers.handle_2qubit),
        (clifford.MeasureZ, handlers.handle_measure),
        (clifford.MeasurePauli, handlers.handle_measure_pauli),
        (clifford.ApplyPauli, handlers.handle_apply_pauli),
    ]
    for name in [gate.name] + list(gate.aliases or [])
}


class StimEmulator:

    def eval(self, circuit: Circuit, *, shots: int) -> Iterable[tuple[bool]]:
        context = Context()

        for inst in [i for i in circuit.instructions if isinstance(i, Instruction)]:
            if inst.name in handlers:
                handlers[inst.name](inst, context)
            else:
                assert False, f"Invalid instruction: {inst}. Valid instructions are: {handlers.keys()}."

        logger.debug(context.circuit)

        sampler = context.circuit.compile_sampler()

        def bitstring(outcome, context: Context):
            result = [False] * circuit.register_count
            for idx, o in context.measurements_map.items():
                result[idx] = int(outcome[o])
            return tuple(result)

        return [bitstring(outcome, context) for outcome in sampler.sample(shots=shots)]
