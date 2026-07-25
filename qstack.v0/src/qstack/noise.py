"""
This module defines noise channels for quantum systems,
including the base class `NoiseChannel` and specific implementations
such as `NoiselessChannel`, `DepolarizingNoise`, and `PauliNoise`.
"""

from abc import ABC, abstractmethod
import numpy as np
from qstack.instruction_set import QuantumDefinition


class NoiseChannel(ABC):
    """
    Abstract base class for noise channels.

    Methods:
        get_kraus_matrices(quantum_def: QuantumDefinition):
            Abstract method to return a list of Kraus matrices for a given QuantumDefinition.
    """

    @abstractmethod
    def get_kraus_matrices(self, quantum_def: QuantumDefinition):
        """Given a QuantumDefinition, return a list of Kraus matrices."""
        pass


class NoiselessChannel(NoiseChannel):
    """
    Represents a noiseless quantum channel.
    """

    def get_kraus_matrices(self, quantum_def: QuantumDefinition):
        targets_length = quantum_def.targets_length
        dim = 2**targets_length
        return [np.eye(dim)]  # Identity matrix with correct dimensions


class DepolarizingNoise(NoiseChannel):
    """
    Represents a depolarizing noise channel.

    Depolarizing noise is a type of quantum noise that affects all gates uniformly.
    It introduces errors by randomly replacing the quantum state with a completely
    mixed state with a certain probability. This noise model is widely used to simulate
    the effects of decoherence and other imperfections in quantum systems.

    Constructor Arguments:
        error_probability (float):
            The probability of an error occurring in the channel.
    """

    def __init__(self, error_probability: float):
        self.error_probability = error_probability

    def get_kraus_matrices(self, quantum_def: QuantumDefinition):
        targets_length = quantum_def.targets_length  # Correct attribute
        dim = 2**targets_length

        # Noiseless effect scaled by (1 - error_probability)
        kraus_operators = [np.sqrt(1 - self.error_probability) * np.eye(dim)]

        # Generate depolarizing noise operators
        for i in range(dim):
            for j in range(dim):
                if i != j:
                    noise_matrix = np.zeros((dim, dim))
                    noise_matrix[i, j] = np.sqrt(self.error_probability / (dim * (dim - 1)))
                    kraus_operators.append(noise_matrix)

        return kraus_operators


class PauliNoise(NoiseChannel):
    """
    Represents a Pauli noise channel.

    Pauli noise applies one of the Pauli operations (X, Y, Z) to the quantum state
    with equal probability. This noise model is useful for simulating errors
    that occur due to bit flips, phase flips, or both.

    Constructor Arguments:
        error_probability (float):
            The total probability of a Pauli error occurring in the channel.
    """

    def __init__(self, error_probability: float):
        self.error_probability = error_probability

    def get_kraus_matrices(self, quantum_def: QuantumDefinition):
        targets_length = quantum_def.targets_length
        dim = 2**targets_length

        # Calculate probabilities for each Pauli operator
        p_x = p_y = p_z = self.error_probability / 3
        p_identity = 1 - self.error_probability

        # Define Pauli matrices
        pauli_x = np.array([[0, 1], [1, 0]])
        pauli_y = np.array([[0, -1j], [1j, 0]])
        pauli_z = np.array([[1, 0], [0, -1]])

        # Generate Kraus operators
        kraus_operators = [
            np.sqrt(p_identity) * np.eye(dim),
            np.sqrt(p_x) * pauli_x,
            np.sqrt(p_y) * pauli_y,
            np.sqrt(p_z) * pauli_z,
        ]

        return kraus_operators
