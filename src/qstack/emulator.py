import logging
import random

from typing import Set
from .qpu import QPU
from .layer import InstructionDefinition, Layer
from .ast import Instruction, QubitId

from qsharp.noisy_simulator import StateVectorSimulator, Operation, Instrument

logger = logging.getLogger("qstack")


class StateVectorEmulator(QPU):

    def __init__(self, instructions: Set[InstructionDefinition]):
        super().__init__()

        operations = {}

        # Create a combined noise operator for each gate
        for inst in instructions:
            if len(inst.parameters) > 0:

                def operation_maker(*args) -> Operation:
                    return Operation([inst.action(*args)])

                operations[inst.name.lower()] = operation_maker
            else:
                logger.debug(f"Found gate {inst.name}: {inst.matrix}")
                operations[inst.name.lower()] = Operation([inst.action()])
        self.operations = operations

        # Create instruments. (TODO: wording, names!)
        projectors = [
            Operation(
                [
                    [[1.0, 0.0], [0.0, 0.0]],
                ]
            ),
            Operation(
                [
                    [[0.0, 0.0], [0.0, 1.0]],
                ]
            ),
        ]
        self.instrument = Instrument(projectors)

    def restart(self, num_qubits: int):
        logger.debug(f"restart: {num_qubits}")
        self.sim = StateVectorSimulator(num_qubits, seed=random.randint(0, 1000))
        self.allocations = {}
        self.mappings = {}
        self.next_id = 0
        self.num_qubits = num_qubits

    def allocate(self, target: QubitId) -> int:
        assert target not in self.mappings, f"Qubit {target} is already allocated"
        self.allocations[self.next_id] = target
        self.mappings[target] = self.next_id
        self.next_id += 1

    def eval(self, instruction: Instruction):
        logger.debug(f"eval: {instruction}")
        gate_name = instruction.name.lower()
        qubits = [self.mappings[t] for t in instruction.targets]
        qubits = [self.num_qubits - int(t) - 1 for t in qubits]
        qubits.reverse()

        assert gate_name in self.operations, f"Invalid instruction {instruction.name}"
        operation = self.operations.get(gate_name)
        if callable(operation):
            self.sim.apply_operation(operation(*instruction.parameters), qubits)
        else:
            self.sim.apply_operation(operation, qubits)
            return None

    def measure(self):
        self.next_id -= 1
        qubits = [self.num_qubits - 1 - self.next_id]
        outcome: int = self.sim.sample_instrument(self.instrument, qubits)
        logger.debug(f"outcome: {outcome}")

        target = self.allocations[self.next_id]
        del self.mappings[target]
        del self.allocations[self.next_id]

        return outcome

    @staticmethod
    def from_layer(layer: Layer):
        return StateVectorEmulator(layer.instructions)
