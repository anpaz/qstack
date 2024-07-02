from dataclasses import dataclass
from typing import Any


@dataclass
class Comment:
    value: str

    def __repr__(self):
        return f'# {self.value}'


@dataclass
class QubitId():
    value: int

    def __repr__(self):
        return str(self.value)


@dataclass
class RegisterId():
    value: int

    def __repr__(self):
        return f"${self.value}"


@dataclass
class Attribute:
    name: str
    value: str | None = None

    def __repr__(self):
        if self.value:
            return f"@{self.name}:{self.value}"
        else:
            return f"@{self.name}"


@dataclass
class Tick:
    def __repr__(self):
        return "\n----"


@dataclass
class Instruction:
    operation: str
    targets: list[QubitId|RegisterId] | None
    parameters: list[str|int|float|tuple] | None = None
    attributes: list[Attribute] | None = None
    comment: Comment | None = None

    def __repr__(self):
        value = f"{self.operation}"
        
        if self.parameters:
            value += "(" + ", ".join([str(t) for t in self.parameters]) + ")"
        if self.targets:
            value += " " + " ".join([str(t) for t in self.targets])
        if self.attributes:
            value += "           " + ", ".join([str(t) for t in self.attributes])
        if self.comment:
            value += "           " + str(self.comment)
        return value


@dataclass
class Circuit:
    name: str
    instruction_set: str
    instructions: list[Comment|Attribute|Tick|Instruction]

    def __repr__(self):
        name = f"name: {self.name}" 
        inst_set = f"instruction set: {self.instruction_set}"
        line = '-' * max(len(name), len(inst_set))
        return f"# {line}\n" + \
               f"# {name}\n" + \
               f"# {inst_set}\n" + \
               f"# {line}\n" + \
               "\n".join([ str(i) for i in self.instructions])
        

