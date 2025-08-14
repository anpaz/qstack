from dataclasses import dataclass
from typing import Optional

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
        pre = "  " * indent
        result = pre + self.name

        if self.parameters:
            args = ",".join([f"{k}={v}" for k, v in self.parameters.items()])
            result += f"({args})"

        if self.targets:
            result += " " + " ".join([str(t) for t in self.targets])

        return result

    def __str__(self):
        return self.print()


@dataclass(frozen=True)
class ClassicInstruction:
    name: str
    parameters: dict[str, ParameterValue] | None = None

    @property
    def depth(self):
        return 0

    def print(self, indent: int = 0) -> str:
        pre = "  " * indent
        result = pre + "?? " + self.name
        if self.parameters:
            args = ",".join([f"{k}={v}" for k, v in self.parameters.items()])
            return result + f"({args})"
        else:
            return result

    def __str__(self):
        return self.print()


@dataclass(frozen=True)
class Kernel:
    target: QubitId | None
    instructions: tuple[QuantumInstruction]
    callback: ClassicInstruction | None = None

    @property
    def depth(self):
        sub_kernels = [k for k in self.instructions if isinstance(k, Kernel)]
        if len(sub_kernels) == 0:
            return 1 if self.target else 0
        else:
            target_depth = 1 if self.target else 0
            return target_depth + max(k.depth for k in sub_kernels)

    def print(self, indent: int = 0) -> str:
        pre = "  " * indent

        result = ""
        if self.target:
            result += pre + "allocate " + str(self.target) + ":\n"
            for i in self.instructions:
                result += i.print(indent + 1) + "\n"
            result += pre + "measure"
        else:
            result += "\n".join([pre + "---"] + [i.print(indent) for i in self.instructions])

        if self.callback:
            if result:
                result += "\n"
            result += pre + str(self.callback)

        return result

    def __str__(self):
        return self.print()

    @staticmethod
    def empty() -> "Kernel":
        return Kernel(target=None, instructions=(), callback=None)

    @staticmethod
    def allocate(
        *targets: str, instructions: list[QuantumInstruction], callback: Optional[ClassicInstruction] = None
    ) -> "Kernel":
        if len(targets) == 0:
            return Kernel(target=None, instructions=tuple(instructions), callback=callback)
        elif len(targets) == 1:
            return Kernel(target=QubitId.wrap(targets[0]), instructions=tuple(instructions), callback=callback)
        else:
            # For multiple targets, create nested kernels recursively
            # Start with the innermost kernel (last target) containing the actual instructions
            innermost = Kernel(target=QubitId.wrap(targets[-1]), instructions=tuple(instructions), callback=None)

            # Build outward, each kernel contains the next inner kernel as its only instruction
            for target in reversed(targets[:-1]):
                innermost = Kernel(target=QubitId.wrap(target), instructions=(innermost,), callback=None)

            # The callback goes on the outermost kernel
            if callback:
                return Kernel(target=innermost.target, instructions=innermost.instructions, callback=callback)
            return innermost

    @staticmethod
    def continue_with(callback: ClassicInstruction) -> "Kernel":
        return Kernel(target=None, instructions=(), callback=callback)
