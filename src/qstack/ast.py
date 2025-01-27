from dataclasses import dataclass, replace
from typing import Callable

type Outcome = tuple[int]


@dataclass(frozen=True)
class QubitId:
    value: str

    @staticmethod
    def wrap(id):
        if isinstance(id, QubitId):
            return id
        return QubitId(id)

    def __str__(self):
        return str(self.value)


type ParameterValue = complex | float | int | QubitId | str


@dataclass(frozen=True)
class Instruction:
    name: str
    targets: tuple[QubitId]
    parameters: dict[str, ParameterValue] | None = None

    def print(self, indent=0):
        pre = " " * indent
        return pre + str(self)

    def __str__(self):
        value = f"{self.name}"

        if self.parameters:
            value += "(" + ", ".join([str(t) for t in self.parameters]) + ")"
        if self.targets:
            value += " " + " ".join([str(t) for t in self.targets])
        return value


class Kernel:
    @property
    def depth(self):
        pass

    @staticmethod
    def allocate(*targets: str, compute=list[Instruction]) -> "Kernel":
        return QuantumKernel(targets=[QubitId.wrap(q) for q in targets], instructions=compute)

    @staticmethod
    def continue_with(continuation: "ContinuationKernel"):
        return continuation

    @staticmethod
    def decode_with(decode: "DecoderKernel"):
        return decode


@dataclass(frozen=True)
class ContinuationKernel:
    name: str
    parameters: dict[str, ParameterValue] | None = None

    @property
    def depth(self):
        return 0

    def print(self, indent: int = 0) -> str:
        pre = " " * indent
        return pre + ">> " + self.name

    def __str__(self):
        return self.print()


@dataclass(frozen=True)
class DecoderKernel:
    name: str
    parameters: dict[str, ParameterValue] | None = None

    @property
    def depth(self):
        return 0

    def print(self, indent: int = 0) -> str:
        pre = " " * indent
        return pre + ">> " + self.name

    def __str__(self):
        return self.print()


@dataclass(frozen=True)
class QuantumKernel:
    targets: tuple[QubitId]
    instructions: tuple[Instruction | Kernel]

    @property
    def depth(self):
        sub_kernels = [k for k in self.instructions if isinstance(k, Kernel)]
        if len(sub_kernels) == 0:
            return len(self.targets)
        else:
            return len(self.targets) + max(k.depth for k in sub_kernels)

    def print(self, indent: int = 0) -> str:
        pre = " " * indent
        result = pre + "allocate " + " ".join(str(q) for q in self.targets) + ":\n"
        for i in self.instructions:
            result += i.print(indent + 1) + "\n"
        result += pre + "measure"

        return result

    def __str__(self):
        return self.print()
