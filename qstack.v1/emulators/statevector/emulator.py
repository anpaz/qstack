from os import path
import random
from qstack.gadget import Instruction
from qsharp.noisy_simulator import StateVectorSimulator, Operation, Instrument
from qstack.noise import NoiseModel

import logging

logger = logging.getLogger("qstack")


class StateVectorEmulator:

    def __init__(self, num_qubits: int, noise_model: NoiseModel | str | None = None) -> None:
        if noise_model is None:
            noise_model = "noiseless"

        if isinstance(noise_model, str):
            noisy_gate_set = NoiseModel()
            noisy_gate_set.find_and_load_model(noise_model)
            noise_model = noisy_gate_set

        assert isinstance(noise_model, NoiseModel), f"Expecting a NoiseModel as parameter, got {noise_model}"

        (gates, instruments) = noise_model.get_noisy_gates_and_instruments(noise_model.default_model)

        operations = {}
        measurements = {}
        # Create a combined noise operator for each gate
        for gate_name in gates.keys():
            gate = gates[gate_name]
            if callable(gate):

                def operation_maker(*args) -> Operation:
                    return Operation(gate(*args))

                operations[gate_name.lower()] = operation_maker
            else:
                logger.debug(f"Found gate {gate_name}: {gate}")
                operations[gate_name.lower()] = Operation(gate)

        # Create instruments. (TODO: wording, names!)
        for gate_name in instruments.keys():
            projectors = []
            for choice in instruments[gate_name]:
                logger.debug(f"Found instrument {gate_name}: {choice[0]}")
                projectors.append(Operation(choice[0]))
            measurements[gate_name.lower()] = Instrument(projectors)

        self.num_qubits = num_qubits
        self.operations = operations
        self.measurements = measurements
        self.sim = StateVectorSimulator(num_qubits)

    def restart(self, num_qubits: int | None = None):
        logger.debug(f"restart: {num_qubits}")
        num_qubits = num_qubits or self.num_qubits
        self.sim = StateVectorSimulator(num_qubits, seed=random.randint(0, 1000))

    def eval(self, instruction: Instruction):
        logger.debug(f"eval: {instruction}")
        gate_name = instruction.name.lower()
        qubits = [int(t.value) for t in instruction.targets]
        qubits = [self.num_qubits - int(t) - 1 for t in qubits]
        qubits.reverse()

        if gate_name in self.operations:
            noisy_gate = self.operations.get(gate_name)
            if callable(noisy_gate):
                self.sim.apply_operation(noisy_gate(*instruction.parameters), qubits)
            else:
                self.sim.apply_operation(noisy_gate, qubits)
                return None

        # Handle the instruments
        if gate_name in self.measurements:
            noisy_instrument = self.measurements[gate_name]
            outcome: int = self.sim.sample_instrument(noisy_instrument, qubits)
            logger.debug(f"outcome: {outcome}")
            return (outcome,)

        assert False, f"Instruction {gate_name} is not supported."
