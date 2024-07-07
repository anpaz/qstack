from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np

from qcir.circuit import Attribute, Comment, Instruction, QubitId, RegisterId


@dataclass(frozen=True)
class InstructionDefinition:
    name: str
    targets: tuple
    parameters: tuple | None = None

    def __call__(
        self,
        targets: list[QubitId | RegisterId] | None,
        parameters: list[str | int | float | tuple] | None = None,
        attributes: list[Attribute] | None = None,
        comment: Comment | None = None,
    ):
        assert [type(t) for t in targets] == self.targets
        if parameters:
            assert [type(t) for t in parameters] == self.parameters
        else:
            assert parameters is None

        return Instruction(
            name=self.name, targets=targets, parameters=parameters, attributes=attributes, comment=comment
        )
