from dataclasses import dataclass
from typing import Iterable

from qstack.gadget import Instruction
from qstack.noise import NoiseModel

from .context import Context
from . import handlers


import logging

logger = logging.getLogger("qstack")


handlers = {
    name: handler
    for (name, handler) in [
        ("|0⟩", handlers.handle_prepare),
        ("h", handlers.handle_1qubit),
        ("x", handlers.handle_1qubit),
        # (clifford.Y, handlers.handle_1qubit),
        # (clifford.Z, handlers.handle_1qubit),
        # (clifford.S, handlers.handle_1qubit),
        # (clifford.SX, handlers.handle_1qubit),
        # (clifford.SY, handlers.handle_1qubit),
        # (clifford.SAdj, handlers.handle_1qubit),
        # (clifford.SXAdj, handlers.handle_1qubit),
        # (clifford.SYAdj, handlers.handle_1qubit),
        # (clifford.CX, handlers.handle_2qubit),
        # (clifford.CY, handlers.handle_2qubit),
        # (clifford.CZ, handlers.handle_2qubit),
        ("mz", handlers.handle_measure),
        # (clifford.MeasurePauli, handlers.handle_measure_pauli),
        # (clifford.ApplyPauli, handlers.handle_apply_pauli),
    ]
    # for name in [gate] + list(gate.aliases or [])
}


class StimEmulator:
    def __init__(self, noise: NoiseModel | None = None) -> None:
        self.noise = noise

    def eval(self, circuit: list[Instruction], *, shots: int) -> Iterable[tuple[bool]]:
        context = Context()
        if self.noise:
            context.noise_1qubit_gate = self.noise.one_qubit_gate_error
            context.noise_2qubit_gate = self.noise.two_qubit_gate_error
            context.noise_measure = self.noise.measurement_error

        for inst in [i for i in circuit]:
            if inst.name in handlers:
                handlers[inst.name](inst, context)
            else:
                assert False, f"Invalid instruction: {inst}. Valid instructions are: {handlers.keys()}."

        logger.debug(context.circuit)

        sampler = context.circuit.compile_sampler()

        return [tuple(int(x) for x in shot) for shot in sampler.sample(shots=shots)]

        # return [bitstring(outcome, context) for outcome in sampler.sample(shots=shots)]
