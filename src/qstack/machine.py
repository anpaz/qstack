from collections import Counter, OrderedDict

from .processors import QPU, CPU, flush
from .program import Program
from .ast import Kernel
from .stack import Stack
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

        for q in kernel.targets:
            self.qpu.allocate(q)

        for instruction in kernel.instructions:
            if isinstance(instruction, Kernel):
                self.eval_kernel(instruction)
            else:
                self.qpu.eval(instruction)

        for _ in kernel.targets:
            self.cpu.collect(self.qpu.measure())

        if kernel.callback:
            continuation = self.cpu.eval(kernel.callback)
            self.eval_kernel(continuation)

    def single_shot(self, program: Program):
        self.qpu.restart(num_qubits=program.depth)
        self.cpu.restart()

        for kernel in program.kernels:
            self.eval_kernel(kernel)

        return tuple(flush(self.cpu))

    def eval(self, program: Program, *, shots: int | None = 1000) -> Results:
        return Results([self.single_shot(program) for _ in range(shots)])


def local_machine_for(stack: Stack) -> QuantumMachine:
    from .classic_processor import from_stack as get_cpu
    from .emulator import from_stack as get_qpu

    cpu = get_cpu(stack)
    qpu = get_qpu(stack)
    return QuantumMachine(qpu=qpu, cpu=cpu)


def local_noisy_machine_for(stack: Stack, noise: NoiseChannel) -> QuantumMachine:
    from .classic_processor import from_stack as get_cpu
    from .emulator import from_stack as get_qpu

    cpu = get_cpu(stack)
    qpu = get_qpu(stack, noise)
    return QuantumMachine(qpu=qpu, cpu=cpu)
