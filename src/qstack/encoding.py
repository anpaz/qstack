"""Portable stabilizer specification for a single logical qubit."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from xdsl.ir import Attribute

from qstack.dialect import QubitType


@dataclass(frozen=True)
class Encoding:
    """Signed Pauli words in bundle order (leftmost letter is wire zero)."""

    physical_qubits: int
    stabilizers: tuple[str, ...]
    logical_x: str
    logical_z: str

    def __post_init__(self) -> None:
        n = self.physical_qubits
        if type(n) is not int or n < 1 or len(self.stabilizers) != n - 1:
            raise ValueError("one logical qubit requires n - 1 stabilizers")
        for word in (*self.stabilizers, self.logical_x, self.logical_z):
            if len(word) != n + 1 or word[0] not in "+-" or set(word[1:]) - set("IXYZ"):
                raise ValueError(f"invalid signed Pauli word {word!r} for width {n}")

    @classmethod
    def identity(cls) -> Encoding:
        return cls(1, (), "+X", "+Z")

    @property
    def is_identity(self) -> bool:
        return self == self.identity()

    def map_types(self, source_types: Sequence[Attribute]) -> tuple[Attribute, ...]:
        """Expand each source qubit into its ordered bundle of physical qubits."""
        if self.physical_qubits == 1:
            return tuple(source_types)
        return tuple(
            typ
            for typ in source_types
            for _ in range(self.physical_qubits if isinstance(typ, QubitType) else 1)
        )

    @classmethod
    def from_dict(cls, data: dict) -> Encoding:
        return cls(data["physical_qubits"], tuple(data["stabilizers"]), data["logical_x"], data["logical_z"])
