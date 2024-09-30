from dataclasses import dataclass


@dataclass
class NoiseModel:
    one_qubit_gate_error: float
    two_qubit_gate_error: float
    measurement_error: float


def simple_noise_model(error_rate: float):
    return NoiseModel(0.0, 0.0, error_rate)
