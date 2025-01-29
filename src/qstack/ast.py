from dataclasses import dataclass, replace
from typing import Callable, Optional

type Outcome = tuple[int]

type ParameterValue = complex | float | int | QubitId | str


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


@dataclass(frozen=True)
class QuantumInstruction:
    name: str
    targets: tuple[QubitId]
    parameters: dict[str, ParameterValue] | None = None

    def print(self, indent=0):
        pre = " " * indent
        result = pre + str(self)
        if self.parameters:
            args = ",".join([f"{k}={v}" for k, v in self.parameters.items()])
            return result + f"({args})"
        else:
            return result

    def __str__(self):
        value = f"{self.name}"

        if self.parameters:
            value += "(" + ", ".join([str(t) for t in self.parameters]) + ")"
        if self.targets:
            value += " " + " ".join([str(t) for t in self.targets])
        return value


@dataclass(frozen=True)
class ClassicInstruction:
    name: str
    callback: str
    parameters: dict[str, ParameterValue] | None = None

    @property
    def depth(self):
        return 0

    def print(self, indent: int = 0) -> str:
        pre = " " * indent
        result = pre + ">> " + self.name
        if self.parameters:
            args = ",".join([f"{k}={v}" for k, v in self.parameters.items()])
            return result + f"({args})"
        else:
            return result

    def __str__(self):
        return self.print()


@dataclass(frozen=True)
class Kernel:
    targets: tuple[QubitId]
    instructions: tuple[QuantumInstruction]
    callback: ClassicInstruction | None = None

    @property
    def depth(self):
        sub_kernels = [k for k in self.instructions if isinstance(k, Kernel)]
        if len(sub_kernels) == 0:
            return len(self.targets)
        else:
            return len(self.targets) + max(k.depth for k in sub_kernels)

    def print(self, indent: int = 0) -> str:
        pre = " " * indent

        result = ""
        if self.targets:
            result += pre + "allocate " + " ".join(str(q) for q in self.targets) + ":\n"
            for i in self.instructions:
                result += i.print(indent + 1) + "\n"
            result += pre + "measure"
        else:
            result += "\n".join([i.print(indent) for i in self.instructions])

        if self.callback:
            if result:
                result += "\n"
            result += pre + str(self.callback)

        return result

    def __str__(self):
        return self.print()

    @staticmethod
    def empty() -> "Kernel":
        return Kernel(targets=(), instructions=(), callback=None)

    @staticmethod
    def allocate(
        *targets: str, compute=list[QuantumInstruction], continue_with: Optional[ClassicInstruction] = None
    ) -> "Kernel":
        return Kernel(
            targets=tuple([QubitId.wrap(q) for q in targets]), instructions=tuple(compute), callback=continue_with
        )

    @staticmethod
    def continue_with(callback: ClassicInstruction) -> "Kernel":
        return Kernel(targets=(), instructions=(), callback=callback)
