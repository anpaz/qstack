from dataclasses import dataclass, replace
from typing import Callable


@dataclass(frozen=True)
class QubitId:
    value: str

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
        return value


type Outcome = tuple[int]
type Continuation = Callable[[Outcome], Kernel]


@dataclass(frozen=True)
class Kernel:
    target: QubitId | None
    instructions: list[Instruction]
    continuation: Continuation | None

    def compute(self, *instructions: Instruction) -> "Kernel":
        return replace(self, instructions=self.instructions + instructions)


def allocate(target: str):
    return Kernel(target=QubitId(target), instructions=[], continuation=None)
