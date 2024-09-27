from collections import Counter
from matplotlib import pyplot as plt

from qstack.quantum_kernel import QuantumKernel


class Outcome:
    def __init__(self, shots, data):
        self.shots = shots
        self.data = data
        self._histogram = None

    def get_histogram(self):
        if not self._histogram:
            self._histogram = dict(Counter(self.data))
        return self._histogram

    def plot_histogram(self):
        histogram = self.get_histogram()
        plt.bar([str(key) for key in histogram.keys()], histogram.values())
        plt.xlabel("Outcomes")
        plt.ylabel("Frequency")
        plt.show()


class Backend:
    def __init__(self, emulator) -> None:
        self.emulator = emulator

    def start(self) -> int:
        return 0

    def eval(self, kernel: QuantumKernel, *, shots: int | None = 1000) -> Outcome:
        def call_emulator():
            outcomes = self.emulator.eval(kernel.circuit, shots=shots)
            for outcome in outcomes:
                outcome = kernel.decoder(outcome)
                if outcome is not None:
                    yield outcome

        return Outcome(shots, list(call_emulator()))

    @property
    def memory(self) -> tuple[bool, ...]:
        return self.backend.memory
