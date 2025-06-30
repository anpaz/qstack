from collections import Counter, OrderedDict
from typing import Callable

from .instruction_set import InstructionSet
from .processors import QPU, CPU
from .program import Program
from .ast import Kernel, QubitId
from .noise import NoiseChannel


class Results:
    def __init__(self, all_data: list[tuple]):
        self.shots = len(all_data)
        self.data = all_data
        self._histogram = None

    def get_histogram(self):
        if not self._histogram:
            hist = Counter(self.data)
            self._histogram = OrderedDict()
            for key in sorted(hist.keys(), key=lambda x: tuple([str(i) for i in x if i])):
                self._histogram[key] = hist[key]
        return self._histogram

    def plot_histogram(self):
        import matplotlib.pyplot as plt

        histogram = self.get_histogram()
        plt.bar([str(key) for key in histogram.keys()], histogram.values())
        plt.xlabel("Outcomes")
        plt.ylabel("Frequency")
        plt.show()


class QuantumMachine:
    def __init__(self, qpu: QPU, cpu: CPU) -> None:
        self.qpu = qpu
        self.cpu = cpu

    def eval_kernel(self, kernel: Kernel) -> None:
        if not kernel:
            return

        if kernel.target:
            self.qpu.allocate(QubitId.wrap(kernel.target))

        for instruction in kernel.instructions:
            if isinstance(instruction, Kernel):
                self.eval_kernel(instruction)
            else:
                self.qpu.eval(instruction)

        outcome = self.qpu.measure() if kernel.target else None

        continuation = self.cpu.eval(kernel.callback, outcome)
        self.eval_kernel(continuation)

    def single_shot(self, program: Program):
        self.cpu.restart()
        self.qpu.restart(num_qubits=program.depth)

        for kernel in program.kernels:
            self.eval_kernel(kernel)

        return tuple(self.cpu.context)

    def eval(self, program: Program, *, shots: int | None = 1000) -> Results:
        return Results([self.single_shot(program) for _ in range(shots)])


def create_callbacks(*definitions: list[Callable]):
    from .classic_processor import ClassicDefinition

    instructions = set([ClassicDefinition.from_callback(callback) for callback in definitions])
    return instructions


def local_machine_for(instruction_set: InstructionSet, callbacks=None) -> QuantumMachine:
    from .classic_processor import from_callbacks as get_cpu
    from .emulator import from_instruction_set as get_qpu

    cpu = get_cpu(callbacks)
    qpu = get_qpu(instruction_set)
    return QuantumMachine(qpu=qpu, cpu=cpu)


def local_noisy_machine_for(instruction_set: InstructionSet, noise: NoiseChannel, callbacks=None) -> QuantumMachine:
    from .classic_processor import from_callbacks as get_cpu
    from .emulator import from_instruction_set as get_qpu

    cpu = get_cpu(callbacks)
    qpu = get_qpu(instruction_set, noise)
    return QuantumMachine(qpu=qpu, cpu=cpu)
