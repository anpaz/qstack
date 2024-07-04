from dataclasses import dataclass


@dataclass(frozen=True)
class Comment:
    value: str

    def __repr__(self):
        return f"# {self.value}"


@dataclass(frozen=True)
class QubitId:
    value: int

    def __repr__(self):
        return str(self.value)


@dataclass(frozen=True)
class RegisterId:
    value: int

    def __repr__(self):
        return f"${self.value}"


@dataclass(frozen=True)
class Attribute:
    name: str
    value: str | None = None

    def __repr__(self):
        if self.value:
            return f"@{self.name}:{self.value}"
        else:
            return f"@{self.name}"


@dataclass(frozen=True)
class Tick:
    def __repr__(self):
        return "\n----"


@dataclass(frozen=True)
class Instruction:
    operation: str
    targets: list[QubitId | RegisterId] | None
    parameters: list[str | int | float | tuple] | None = None
    attributes: list[Attribute] | None = None
    comment: Comment | None = None

    def __repr__(self):
        value = f"{self.operation}"

        if self.parameters:
            value += "(" + ", ".join([str(t) for t in self.parameters]) + ")"
        if self.targets:
            value += " " + " ".join([str(t) for t in self.targets])
        if self.attributes:
            value += (" " * max(len(value) + 5, 40)) + ", ".join([str(t) for t in self.attributes])
        if self.comment:
            value += (" " * max(len(value) + 5, 40)) + str(self.comment)
        return value


@dataclass(frozen=True)
class Circuit:
    name: str
    instruction_set: str
    instructions: list[Comment | Attribute | Tick | Instruction]

    def __repr__(self):
        name = f"name: {self.name}"
        inst_set = f"instruction set: {self.instruction_set}"
        line = "-" * max(len(name), len(inst_set))
        return (
            f"# {line}\n"
            + f"# {name}\n"
            + f"# {inst_set}\n"
            + f"# {line}\n"
            + "\n".join([str(i) for i in self.instructions])
        )


def max_register(circuit: Circuit) -> int:
    max = 0
    for i in circuit.instructions:
        for t in i.targets:
            if isinstance(t, RegisterId):
                if t.value > max:
                    max = t.value
    return max


def max_qubit(circuit: Circuit) -> int:
    max = 0
    for i in circuit.instructions:
        for t in i.targets:
            if isinstance(t, QubitId):
                if t.value > max:
                    max = t.value
    return max


def circuit_dimensions(circuit: Circuit) -> tuple[int, int, int]:
    max_q = -1
    max_r = -1
    instr_count = 0

    for i in circuit.instructions:
        if isinstance(i, Instruction):
            instr_count += 1
            for t in i.targets:
                if isinstance(t, RegisterId):
                    if t.value > max_r:
                        max_r = t.value
                elif isinstance(t, QubitId):
                    if t.value > max_r:
                        max_q = t.value
                else:
                    assert False, "Unknown target type."
    return (max_q + 1, max_r + 1, instr_count)
