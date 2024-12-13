from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Comment:
    value: str

    def __repr__(self):
        return f"# {self.value}"


@dataclass(frozen=True)
class QubitId:
    value: int | str

    @staticmethod
    def wrap(id):
        if isinstance(id, QubitId):
            return id
        return QubitId(id)

    def __repr__(self):
        return str(self.value)


@dataclass(frozen=True)
class Instruction:
    name: str
    targets: tuple[QubitId]
    parameters: tuple | None = None

    def __str__(self):
        value = f"{self.name}"

        if self.parameters:
            value += "(" + ", ".join([str(t) for t in self.parameters]) + ")"
        if self.targets:
            value += " " + " ".join([str(t) for t in self.targets])
        # if self.attributes:
        #     value += (" " * max(25 - len(value), 5)) + ", ".join([str(t) for t in self.attributes])
        # if self.comment:
        #     value += (" " * max(37 - len(value), 5)) + str(self.comment)
        return value


@dataclass(frozen=True)
class Tick(Instruction):
    def __init__(self):
        super().__init__(name="----", targets=None)


@dataclass(frozen=True)
class GadgetContext:
    allocations: dict[QubitId, int] = field(default_factory=dict)
    next_id: int = 0

    def allocate(self, *targets: QubitId):
        new_qubits = {}
        id = self.next_id
        for q in targets:
            assert q not in self.allocations, f"Qubit {q} is already allocated"
            new_qubits[q] = id
            id += 1
        return self.__class__(allocations=self.allocations | new_qubits, next_id=id)

    def __add__(self, other):
        assert isinstance(other, GadgetContext), f"Only context + context implemented."

        shared = self.allocations.keys() & other.allocations.keys()
        assert len(shared) == 0, f"These qubits were prepared in both contexts: {shared}"

        return self.allocate(*other.allocations.keys())


@dataclass(frozen=True)
class Gadget:
    name: str = "n/a"
    level: int = 0

    # context: GadgetContext = GadgetContext()
    prepare: tuple[Instruction] | None = None
    compute: tuple[Instruction] | None = None
    measure: tuple[Instruction] | None = None
    decode: Callable[[tuple[bool]], tuple[bool] | None] | None = None

    def check(self):
        # TODO: verify the new Gadget is valid:
        # to be valid:
        #   * all target qubits should be allocated
        #   * each qubit can be prepared only once.
        #   * each qubit can be measured only once (?)
        # def check_unique_measures():
        #     all_targets = []
        #     for instr in self.measure:
        #         all_targets.extend(instr.targets)  # Collect all targets from each object
        #     # Check for duplicates by comparing the length of the set and the list
        #     return len(all_targets) == len(set(all_targets))

        # assert check_unique_measures(), "Some qubits measured more than once."
        return self

    def __str__(self):
        def print_list(circuit, needs_tick):
            if circuit:
                result = "\n"
                if needs_tick:
                    result += "------------------------\n"
                result += "\n".join([str(i) for i in circuit])
                needs_tick = True
                return result
            else:
                return ""

        if self.level > 0:
            result = ""
            for g in self.prepare + self.compute + self.measure:
                instr = str(g)
                if instr:
                    result += instr
            if self.decode:
                result += f"\n=========== decoder (level:{self.level}) ==========="
            # else:
            #     result += f"\n------------------------"
            return result

        else:
            result = ""
            for circuit in [self.prepare, self.compute, self.measure]:
                result += print_list(circuit, len(result) > 0)
            if self.decode:
                result += f"\n=========== decoder (level:{self.level}) ==========="
            # else:
            #     result += f"\n------------------------"
            return result

    def __or__(self, other):
        def add_lists(a, b):
            a = list(a) if a else []
            b = list(b) if b else []
            return a + b

        def decoder(bits, context):
            bits1 = tuple()
            bits2 = tuple()
            if self.decode:
                length = sum(len(m.targets) for m in self.measure) if self.measure else 0
                bits1, context = self.decode(bits[:length], context)
            if other.decode:
                length = sum(len(m.targets) for m in other.measure) if other.measure else 0
                bits2, context = other.decode(bits[-length:], context)
            return bits1 + bits2, context

        assert isinstance(other, Gadget), f"Only gadget | gadget implemented."

        prep = add_lists(self.prepare, other.prepare)
        comp = add_lists(self.compute, other.compute)
        meas = add_lists(self.measure, other.measure)
        # context = self.context + other.context
        dec = decoder if (self.decode or other.decode) else None
        return Gadget(name=self.name, prepare=prep, compute=comp, measure=meas, decode=dec).check()
