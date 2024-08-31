import logging

from pyquil import Program, get_qc
from pyquil.api import MemoryMap

from qcir.circuit import Circuit, Instruction

from .context import Context
from . import handlers
import runtimes.matrix.instruction_set as matrix


logger = logging.getLogger("qstack")


class pyQuilEmulator:
    def __init__(self):
        self.handlers = {
            gate.name: handler
            for (gate, handler) in [
                (matrix.Matrix1, handlers.handle_matrix1),
                (matrix.Matrix2, handlers.handle_matrix2),
                (matrix.Measure, handlers.handle_measure),
            ]
        }

    def eval(self, circuit: Circuit, *, shots: int, memory: tuple[int, ...]) -> tuple:
        q_count = circuit.qubit_count
        r_count = len(memory)
        assert q_count < 30, f"Only support simulation of up to 29 qubits, circuit reports: {q_count}"

        program = Program()
        context = Context(constructors={}, program=program, readout=program.declare("readout", "BIT", r_count))

        for inst in [i for i in circuit.instructions if isinstance(i, Instruction)]:
            if inst.name in self.handlers:
                self.handlers[inst.name](inst, context)
            else:
                assert False, f"Invalid instruction: {inst}. Valid instructions are: {pyQuilEmulator.handlers.keys()}."

        logger.debug(context.program)
        context.program.wrap_in_numshots_loop(shots)

        # Get a Quantum Virtual Machine to simulate execution
        qc_name = f"{q_count}q-qvm"
        qc = get_qc(qc_name)
        executable = qc.compile(context.program)
        memory_map = {"readout": memory}
        results = qc.run(executable, memory_map=memory_map)

        bitstrings = results.get_register_map().get("readout")
        return bitstrings
