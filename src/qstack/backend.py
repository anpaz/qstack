from collections import Counter, OrderedDict
from matplotlib import pyplot as plt

from qcir.circuit import Circuit
from qstack.gadget import Gadget


class Outcome:
    def __init__(self, shots, all_data: list[(tuple, tuple)]):
        self.shots = shots
        self.data = [data[0] for data in all_data if data[0] is not None]
        self.raw_data = [data[1] for data in all_data]
        self._histogram = None
        self._raw_histogram = None

    def get_histogram(self):
        if not self._histogram:
            hist = Counter(self.data)
            self._histogram = OrderedDict()
            for key in sorted(hist.keys(), key=lambda x: tuple([str(i) for i in x if i])):
                self._histogram[key] = hist[key]
        return self._histogram

    def plot_histogram(self):
        histogram = self.get_histogram()
        plt.bar([str(key) for key in histogram.keys()], histogram.values())
        plt.xlabel("Outcomes")
        plt.ylabel("Frequency")
        plt.show()

    def get_raw_histogram(self):
        if not self._raw_histogram:
            hist = dict(Counter(self.raw_data))
            self._raw_histogram = OrderedDict()
            for key in sorted(hist.keys()):
                self._raw_histogram[key] = hist[key]
        return self._raw_histogram


class Backend:
    def __init__(self, emulator) -> None:
        self.emulator = emulator

    def start(self) -> int:
        return 0

    def eval(self, gadget: Gadget, *, shots: int | None = 1000) -> Outcome:
        def call_emulator():
            outcomes = self.emulator.eval(gadget.circuit, shots=shots)
            for raw_outcome in outcomes:
                outcome = raw_outcome
                if gadget.decoder:
                    outcome = gadget.decoder(raw_outcome)
                yield outcome, raw_outcome

        return Outcome(shots, list(call_emulator()))

    @property
    def memory(self) -> tuple[bool, ...]:
        return self.backend.memory
