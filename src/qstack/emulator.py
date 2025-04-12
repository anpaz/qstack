import logging
import random

from typing import Set
from qsharp.noisy_simulator import StateVectorSimulator, Operation, Instrument

from .processors import QPU
from .ast import QuantumInstruction, QubitId
from .layer import QuantumDefinition, Layer
from .stack import Stack


logger = logging.getLogger("qstack")


class StateVectorEmulator(QPU):
    def __init__(self, instructions: Set[QuantumDefinition]):
        super().__init__()

        # Create operators:
        operations = {}
        for inst in instructions:
            if inst.matrix is None:
                assert inst.factory is not None, f"Invalid instruction {inst.name}"
                capture = inst

                def operation_maker(**args) -> Operation:
                    return Operation([capture.factory(**args)])

                operations[inst.name.lower()] = operation_maker
            else:
                logger.debug(f"Found gate {inst.name}: {inst.matrix}")
                operations[inst.name.lower()] = Operation([inst.matrix])
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
        gate_name = instruction.name.lower()
        qubits = [self.allocations.index(t) for t in instruction.targets]
        qubits = [self.num_qubits - int(t) - 1 for t in qubits]
        qubits.reverse()

        assert gate_name in self.operations, f"Invalid instruction: {instruction}"
        operation = self.operations.get(gate_name)
        logger.debug(f"eval: {gate_name} {qubits}")
        if callable(operation):
            self.sim.apply_operation(operation(**instruction.parameters), qubits)
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
    return StateVectorEmulator(layer.quantum_definitions)


def from_stack(stack: Stack):
    return from_layer(stack.target.layer)
