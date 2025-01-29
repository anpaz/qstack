import logging
import random

from typing import Set
from .processors import QPU
from .layer import QuantumInstructionDefinition, Layer
from .ast import QuantumInstruction, QubitId

from qsharp.noisy_simulator import StateVectorSimulator, Operation, Instrument

logger = logging.getLogger("qstack")


class StateVectorEmulator(QPU):
    def __init__(self, instructions: Set[QuantumInstructionDefinition]):
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

        # Create instruments.
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
        self.allocations = []
        self.num_qubits = num_qubits

    def allocate(self, target: QubitId) -> int:
        assert target not in self.allocations, f"Qubit {target} is already allocated"
        self.allocations.append(target)

    def eval(self, instruction: QuantumInstruction):
        logger.debug(f"eval: {instruction}")
        gate_name = instruction.name.lower()
        qubits = [self.allocations.index(t) for t in instruction.targets]
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
        id = len(self.allocations) - 1
        qubits = [self.num_qubits - 1 - id]
        outcome: int = self.sim.sample_instrument(self.instrument, qubits)
        logger.debug(f"outcome: {outcome}")
        self.allocations.pop()
        return outcome


def from_layer(layer: Layer):
    return StateVectorEmulator(layer.quantum_instructions)
