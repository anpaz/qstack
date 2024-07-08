import logging
from dataclasses import dataclass

import numpy as np
from pyquil import Program, get_qc
from pyquil.quilatom import MemoryReference

from qcir.circuit import Circuit, Instruction
from qstack import Emulator, Handler, InstructionDefinition

from .context import Context
from .handlers import Matrix1, Matrix2, Measure

logger = logging.getLogger("qstack")


class pyQuilEmulator(Emulator):

    def __init__(self):
        self.handlers: dict[str, Handler] = {
            handler.source.name: handler for handler in [Matrix1(), Matrix2(), Measure()]
        }

    @property
    def instruction_set(self) -> set[InstructionDefinition]:
        return {handler.source for handler in self.handlers.values()}

    def eval(self, circuit: Circuit, *, shots: int) -> tuple:
        q_count, r_count, _ = circuit.get_dimensions()
        assert q_count < 30, f"Only support simulation of up to 29 qubits, circuit reports: {q_count}"

        program = Program()
        context = Context(constructors={}, program=program, readout=program.declare("readout", "BIT", r_count))

        for inst in [i for i in circuit.instructions if isinstance(i, Instruction)]:
            if inst.name in self.handlers:
                self.handlers[inst.name].handle(inst, context)
            else:
                assert False, f"Invalid instruction: {inst}. Valid instructions are: {pyQuilEmulator.handlers.keys()}."

        logger.debug(context.program)
        context.program.wrap_in_numshots_loop(shots)

        # Get a Quantum Virtual Machine to simulate execution
        qc_name = f"{q_count}q-qvm"
        qc = get_qc(qc_name)
        executable = qc.compile(context.program)
        results = qc.run(executable)

        bitstrings = results.get_register_map().get("readout")
        return bitstrings
