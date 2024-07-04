from dataclasses import dataclass
from typing import Any
from .utils import cache_field

import logging

logger = logging.getLogger("qcir")


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

    def get_metadata(self, key: str, default: str = None) -> Any:
        md = cache_field(self, "_metadata", lambda: circuit_metadata(self))
        return md.get(key, default)

    def get_dimensions(self) -> tuple[int, int, int]:
        return cache_field(self, "_dimensions", lambda: circuit_dimensions(self))

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


def circuit_metadata(circuit: Circuit) -> dict[str, str]:
    result = {}
    for inst in circuit.instructions:
        if isinstance(inst, Comment):
            pass
        elif isinstance(inst, Tick) or isinstance(inst, Instruction):
            break
        elif isinstance(inst, Attribute):
            result[inst.name] = inst.value
        else:
            assert False, f"Unknown instruction: {inst}"
    return result


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

    q_count = circuit.get_metadata("qubit_count", max_q + 1)
    if q_count > max_q + 1:
        logger.warning(f"qubit count in metadata ({q_count}) is qubits in the circuit {max_q + 1}")

    r_count = circuit.get_metadata("register_count", max_r + 1)
    if r_count > max_r + 1:
        logger.warning(f"qubit count in metadata ({r_count}) is qubits in the circuit {max_q + 1}")

    return (q_count, r_count, instr_count)
