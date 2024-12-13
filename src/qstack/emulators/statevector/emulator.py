from os import path
import random
from qstack import noise
from qstack.gadget import Instruction
from qsharp.noisy_simulator import StateVectorSimulator, Operation, Instrument
from qstack.noise import noiseless_model, NoiseModel


import logging

logger = logging.getLogger("qstack")


class StateVectorEmulator:

    def __init__(self, num_qubits: int, noise_model: NoiseModel | str | None = None) -> None:
        if noise_model is None:
            noise_model = noiseless_model()
        elif isinstance(noise_model, str):
            relative_to = path.dirname(path.abspath(__file__))
            filename = path.join(relative_to, noise_model)
            noise_model = NoiseModel()
            noise_model.load_config(filename)

        assert isinstance(noise_model, NoiseModel), f"Expecting a NoiseModel as parameter, got {noise_model}"

        (gates, instruments) = noise_model.get_noisy_gates_and_instruments(noise_model.default_model)

        self.operations = {name.lower(): Operation(gates[name]) for name in gates}
        self.measurements = {
            name.lower(): Instrument([Operation(choice[0]) for choice in instruments[name]]) for name in instruments
        }
        self.num_qubits = num_qubits
        self.sim = StateVectorSimulator(num_qubits)

    def reset(self, num_qubits: int | None = None):
        num_qubits = num_qubits or self.num_qubits
        self.sim = StateVectorSimulator(num_qubits, seed=random.randint(0, 1000))

    def eval(self, instruction: Instruction):
        logger.debug(f"eval: {instruction}")
        name = instruction.name
        qubits = [int(t.value) for t in instruction.targets]
        if name in self.operations:
            op = self.operations[name]
            self.sim.apply_operation(op, qubits)
            return None

        # Handle the instruments
        if name in self.measurements:
            noisy_instrument = self.measurements[name]
            outcome = self.sim.sample_instrument(noisy_instrument, qubits)
            logger.debug(f"outcome: {outcome}")
            return (outcome,)

        assert False, f"Instruction {name} is not supported."
