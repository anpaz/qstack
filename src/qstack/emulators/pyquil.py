from pyquil import Program
from pyquil.quil import DefGate
from pyquil.gates import MEASURE
from pyquil import get_qc

from qcir.circuit import Circuit, QubitId, RegisterId, Instruction

from .emulator import Emulator
from ..instruction_definition import InstructionDefinition

import logging
import re

logger = logging.getLogger("qstack")


class pyQuilEmulator(Emulator):

    def __init__(self, instruction_set: set[InstructionDefinition]):
        self.instruction_set = instruction_set
        self.constructors = {}

    def get_operation(self, program, inst: Instruction):
        op_name = inst.operation
        if inst.parameters:
            op_name += "(" + ",".join([str(p) for p in inst.parameters]) + ")"

        if op_name not in self.constructors:
            i = next(filter(lambda i: inst.operation in i.names, self.instruction_set))
            if inst.parameters:
                matrix = i.matrix(*inst.parameters)
            else:
                matrix = i.matrix()
            if matrix is not None:
                gate_name = f"qstack__{len(self.constructors):010}"
                definition = DefGate(gate_name, matrix)
                ctx = definition.get_constructor()
                self.constructors[op_name] = ctx
                program += definition
            else:
                self.constructors[op_name] = None
        return self.constructors[op_name]

    def eval(self, circuit: Circuit, *, shots: int) -> tuple:
        p = Program()
        self.constructors = {}
        q_count, r_count, _ = circuit.get_dimensions()
        readout = p.declare("readout", "BIT", r_count)

        for inst in [i for i in circuit.instructions if isinstance(i, Instruction)]:
            qubits = [t.value for t in inst.targets if isinstance(t, QubitId)]
            registers = [t.value for t in inst.targets if isinstance(t, RegisterId)]
            op = self.get_operation(p, inst)
            if op:
                p += op(*qubits)
            # Measurement operations:
            if len(registers) == 1:
                p += MEASURE(qubits[-1], readout[registers[0]])
            elif len(registers) > 1:
                assert False, f"Invalid instruction: {inst}. Only single measurement supported."

        logger.debug(p)
        p.wrap_in_numshots_loop(shots)

        # Get a Quantum Virtual Machine to simulate execution
        assert q_count < 30, f"Only support simulation of up to 29 qubits, circuit reports: {q_count}"
        qc_name = f"{q_count}q-qvm"
        qc = get_qc(qc_name)
        executable = qc.compile(p)
        results = qc.run(executable)

        bitstrings = results.get_register_map().get("readout")
        return bitstrings
