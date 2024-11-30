from dataclasses import dataclass

from qstack.circuit import Attribute, Comment, Instruction, QubitId


@dataclass(frozen=True)
class GadgetDefinition:
    name: str
    targets: tuple
    parameters: tuple | None = None
    aliases: tuple | None = None

    def __call__(
        self,
        targets: list[QubitId] | None,
        parameters: list[str | int | float | tuple | complex] | None = None,
        attributes: list[Attribute] | None = None,
        comment: Comment | None = None,
    ):
        def check_types(values, expected_types):
            if expected_types[-1] == Ellipsis:
                if len(values) == len(expected_types) - 1:
                    expected_types = expected_types[:-1]
                elif len(values) >= len(expected_types):
                    rest = [expected_types[-2]] * (len(values) - (len(expected_types) - 1))
                    expected_types = expected_types[:-1] + rest
                else:
                    assert False, f"Invalid number of values for operation {self.name}"
            for expected, value in zip(expected_types, values):
                assert isinstance(value, expected), f"Expecting value of type {expected}, got {value}"

        check_types(targets, self.targets)

        if parameters:
            assert self.parameters, f"Instruction {self.name} is not expecting parameters."
            check_types(parameters, self.parameters)
        else:
            assert parameters is None

        return Instruction(
            name=self.name, targets=targets, parameters=parameters, attributes=attributes, comment=comment
        )

    def __hash__(self) -> int:
        t = (
            self.name,
            tuple(self.targets),
            tuple(self.parameters or []),
            tuple(self.aliases or []),
        )
        return hash(t)
