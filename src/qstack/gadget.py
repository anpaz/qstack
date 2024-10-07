from dataclasses import dataclass
from typing import Any, Callable, Set

from qcir.circuit import Attribute, Circuit, Instruction, QubitId, RegisterId, Tick
from .instruction_definition import InstructionDefinition


@dataclass(frozen=True)
class Gadget:
    name: str
    circuit: Circuit
    decoder: Callable[[list[bool]], list[bool] | None] | None = None
    metadata: dict[str, Any] | None = None

    def save(self, filename: str | None = None):
        if not filename:
            filename = f"{self.name}.crc"
        with open(filename, "w", encoding="utf-8") as file:
            file.write(str(self))

    def __repr__(self):
        # for circuit visualization tool:
        coords = [
            "@coords " + "".join([f" {i} ({i} 0)" for i in range(self.circuit.qubit_count)]),
            "@coords " + "".join([f" ${i} ({i} 1)" for i in range(self.circuit.register_count)]),
            "@decoder " + (self.decoder.__name__ if self.decoder else "none"),
            "@view 'wires'",
            "",
        ]
        name = f"name: {self.name}"
        line = "-" * len(name)
        header = f"# {line}\n" + f"# {name}\n" + f"# {line}\n"
        md = self.metadata or []
        attributes = "\n".join([str(m) for m in md] + coords)
        body = str(self.circuit)

        return "\n".join([header, attributes, body])
