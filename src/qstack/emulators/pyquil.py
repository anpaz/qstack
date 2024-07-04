from pyquil import Program
from pyquil.quil import DefGate
from pyquil.gates import MEASURE
from pyquil import get_qc

from qcir.circuit import Circuit, QubitId, RegisterId, circuit_dimensions, Instruction

from .emulator import Emulator
from ..instruction_definition import InstructionDefinition

import logging

logger = logging.getLogger("qstack")


class pyQuilEmulator(Emulator):
    def __init__(self, instruction_set: set[InstructionDefinition]):
        p = Program()
        constructors = {}
        for inst in instruction_set:
            if inst.matrix is not None:
                for name in inst.names:
                    definition = DefGate(name, inst.matrix)
                    ctx = definition.get_constructor()
                    constructors[name] = ctx
                    p += definition
        self._program = p
        self._constructors = constructors

    def eval(self, circuit: Circuit, *, shots: int) -> tuple:
        p = self._program.copy()
        q_count, r_count, _ = circuit_dimensions(circuit)
        readout = p.declare("readout", "BIT", r_count)

        for inst in [i for i in circuit.instructions if isinstance(i, Instruction)]:
            qubits = [t.value for t in inst.targets if isinstance(t, QubitId)]
            registers = [t.value for t in inst.targets if isinstance(t, RegisterId)]

            if inst.operation in self._constructors:
                op = self._constructors[inst.operation]
                p += op(*qubits)

            if len(registers) == 1:
                assert len(qubits) == 1, f"Invalid instruction: {inst}"
                p += MEASURE(qubits[0], readout[registers[0]])
            elif len(registers) > 1:
                assert False, f"Invalid instruction: {inst}"

        logger.debug(p)
        p.wrap_in_numshots_loop(shots)

        # Get a Quantum Virtual Machine to simulate execution
        assert q_count < 29, f"Only support simulation of up to 29 qubits, circuit reports: {q_count}"
        qc_name = f"{q_count}q-qvm"
        qc = get_qc(qc_name)
        executable = qc.compile(p)
        results = qc.run(executable)

        bitstrings = results.get_register_map().get("readout")
        return bitstrings
