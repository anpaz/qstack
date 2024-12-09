from collections import Counter, OrderedDict
from typing import Any
from matplotlib import pyplot as plt

from qstack.gadget import Gadget, Instruction, QubitId
from qstack.emulators.statevector.emulator import StateVectorEmulator
from qstack.noise import NoiseModel


def eval_gadget_with(gadget: Gadget, emulator, context):
    def allocate(targets: list[QubitId]):
        allocations = context.get("allocations", {})
        next_id = context.get("next_id", 0)
        for t in targets:
            assert t not in allocations
            allocations[t] = next_id
            next_id += 1
        context["next_id"] = next_id
        context["allocations"] = allocations

    def deallocate(targets: list[QubitId]):
        allocations = context.get("allocations", {})
        for t in targets:
            assert t in allocations
            del allocations[t]
        context["allocations"] = allocations

    def bind(i: Instruction):
        allocations = context.get("allocations", {})
        assert all(t in allocations for t in i.targets), "Some qubits have not been allocated."
        targets = [QubitId.wrap(allocations[t]) for t in i.targets]
        return Instruction(name=i.name, targets=targets, parameters=i.parameters)

    def eval_one(instr: Instruction, ctx, is_prepare=False, is_measure=False):
        if isinstance(instr, Gadget):
            return eval_gadget_with(gadget=instr, emulator=emulator, context=ctx)
        else:
            targets = instr.targets
            if is_prepare:
                allocate(targets)
            instr = bind(instr)
            raw_outcome = emulator.eval(instr)
            if is_measure:
                deallocate(targets)
            return raw_outcome, ctx

    for instr in gadget.prepare or []:
        _, context = eval_one(instr, context, is_prepare=True)

    for instr in gadget.compute or []:
        _, context = eval_one(instr, context)

    raw_outcome = tuple()
    for instr in gadget.measure or []:
        outcome, context = eval_one(instr, context, is_measure=True)
        raw_outcome += outcome

    outcome = raw_outcome
    if gadget.decode:
        outcome, context = gadget.decode(raw_outcome, context)

    return outcome, context


class Outcome:
    def __init__(self, all_data: list[(tuple, Any)]):
        self.shots = len(all_data)
        self.data = [data[0] for data in all_data if data[0] is not None]
        self._histogram = None

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


class Backend:
    def __init__(self, emulator, qubit_count=30) -> None:
        self.emulator = emulator

    def single_shot(self, gadget: Gadget):
        self.emulator.reset()
        return eval_gadget_with(gadget, self.emulator, context={})

    def eval(self, gadget: Gadget, *, shots: int | None = 1000) -> Outcome:
        return Outcome([self.single_shot(gadget) for _ in range(shots)])


class StateVectorBackend(Backend):
    def __init__(self, num_qubits=12, noise: NoiseModel | str | None = None) -> None:
        super().__init__(StateVectorEmulator(noise_model=noise, num_qubits=num_qubits))
