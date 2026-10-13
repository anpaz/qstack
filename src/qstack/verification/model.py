"""Portable, single-step witness data shared by qstack and rule backends."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Literal

import numpy as np
from xdsl.dialects.builtin import FloatAttr, IntegerAttr
from xdsl.ir import Operation

from qstack.dialect.core import UnitaryGateOp


@dataclass(frozen=True)
class ValueRef:
    """One SSA value in a kernel: an entry argument or an operation result."""

    kind: Literal["arg", "result"]
    index: int
    slot: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValueRef:
        return cls(data["kind"], int(data["index"]), int(data.get("slot", 0)))


@dataclass(frozen=True)
class Edge:
    id: str
    kernel: str
    source: tuple[ValueRef, ...]
    target: tuple[ValueRef, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Edge:
        return cls(
            str(data["id"]),
            str(data["kernel"]),
            tuple(ValueRef.from_dict(item) for item in data["source"]),
            tuple(ValueRef.from_dict(item) for item in data["target"]),
        )


@dataclass(frozen=True)
class Gate:
    """A gate on ordered circuit wires, including its matrix semantics."""

    name: str
    wires: tuple[int, ...]
    parameters: tuple[tuple[str, float], ...]
    matrix: tuple[tuple[tuple[float, float], ...], ...]
    attributes: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_op(cls, op: Operation, wires: tuple[int, ...]) -> Gate:
        if not isinstance(op, UnitaryGateOp):
            raise TypeError(f"{op.name} has no unitary semantics")
        parameters: list[tuple[str, float]] = []
        for name, value in sorted(op.properties.items()):
            if isinstance(value, FloatAttr):
                parameters.append((name, float(value.value.data)))
            elif isinstance(value, IntegerAttr):
                parameters.append((name, float(value.value.data)))
            else:
                raise TypeError(f"unsupported gate parameter {name} on {op.name}")
        matrix = np.asarray(op.unitary(), dtype=complex)
        return cls(
            op.name,
            wires,
            tuple(parameters),
            tuple(
                tuple((float(value.real), float(value.imag)) for value in row)
                for row in matrix
            ),
            tuple((name, str(value)) for name, value in sorted(op.attributes.items())),
        )

    def array(self) -> np.ndarray:
        return np.array(
            [[complex(real, imag) for real, imag in row] for row in self.matrix],
            dtype=complex,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Gate:
        return cls(
            str(data["name"]),
            tuple(int(wire) for wire in data["wires"]),
            tuple((str(name), float(value)) for name, value in data["parameters"]),
            tuple(
                tuple((float(real), float(imag)) for real, imag in row)
                for row in data["matrix"]
            ),
            tuple((str(name), str(value)) for name, value in data.get("attributes", [])),
        )


@dataclass(frozen=True)
class Circuit:
    width: int
    gates: tuple[Gate, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Circuit:
        return cls(int(data["width"]), tuple(Gate.from_dict(gate) for gate in data["gates"]))


@dataclass(frozen=True)
class PatternOp:
    """A concrete operation and its ordered input wires in a rule pattern."""

    name: str
    operands: tuple[ValueRef, ...]
    result_types: tuple[str, ...]
    properties: tuple[tuple[str, str], ...] = ()
    attributes: tuple[tuple[str, str], ...] = ()
    gate: Gate | None = None
    hosts: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatternOp:
        return cls(
            str(data["name"]),
            tuple(ValueRef.from_dict(item) for item in data["operands"]),
            tuple(str(item) for item in data["result_types"]),
            tuple((str(k), str(v)) for k, v in data["properties"]),
            tuple((str(k), str(v)) for k, v in data["attributes"]),
            None if data["gate"] is None else Gate.from_dict(data["gate"]),
            tuple(str(source) for source in data["hosts"]),
        )


@dataclass(frozen=True)
class Pattern:
    """A small graph with ordered boundary ports, independent of an IR site.

    Argument references name input ports; result references name operation
    outputs. Allocations are explicit zero-input ``qstack.alloc`` nodes.
    Outputs may forward inputs, including an entirely empty target pattern.
    """

    inputs: tuple[str, ...]
    operations: tuple[PatternOp, ...]
    outputs: tuple[ValueRef, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pattern:
        return cls(
            tuple(str(item) for item in data["inputs"]),
            tuple(PatternOp.from_dict(item) for item in data["operations"]),
            tuple(ValueRef.from_dict(item) for item in data["outputs"]),
        )


@dataclass(frozen=True)
class Rule:
    """A reusable rewrite, including syntactic identity and inline rules."""

    id: str
    source: Pattern
    target: Pattern
    kind: Literal["identity", "gate", "inline"]
    callee: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        return cls(
            str(data["id"]), Pattern.from_dict(data["source"]),
            Pattern.from_dict(data["target"]), data["kind"],
            None if data.get("callee") is None else str(data["callee"]),
        )


@dataclass(frozen=True)
class CircuitRule:
    """The portable circuit-only payload sent to existing verifier plugins."""

    id: str
    source: Circuit
    target: Circuit


@dataclass(frozen=True)
class Claim:
    """One application of a named rule, with both IR sites and edge bindings."""

    id: str
    kernel: str
    rule: str
    source_ops: tuple[int, ...]
    target_ops: tuple[int, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    source_allocations: tuple[int, ...] = ()
    target_allocations: tuple[int, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Claim:
        return cls(
            str(data["id"]), str(data["kernel"]), str(data["rule"]),
            tuple(int(index) for index in data["source_ops"]),
            tuple(int(index) for index in data["target_ops"]),
            tuple(str(edge) for edge in data["inputs"]),
            tuple(str(edge) for edge in data["outputs"]),
            tuple(int(index) for index in data["source_allocations"]),
            tuple(int(index) for index in data["target_allocations"]),
        )


@dataclass(frozen=True)
class KernelBoundary:
    name: str
    inputs: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KernelBoundary:
        return cls(str(data["name"]), tuple(str(edge) for edge in data["inputs"]))


@dataclass(frozen=True)
class Witness:
    """A claim graph and reusable rules for one source-to-target step."""

    source_sha256: str
    target_sha256: str
    source_width: int
    target_width: int
    rules: tuple[Rule, ...]
    claims: tuple[Claim, ...]
    edges: tuple[Edge, ...]
    kernels: tuple[KernelBoundary, ...]

    @classmethod
    def bind(
        cls,
        source_module: Any,
        target_module: Any,
        *,
        rules: tuple[Rule, ...],
        claims: tuple[Claim, ...],
        edges: tuple[Edge, ...],
        kernels: tuple[KernelBoundary, ...],
        source_width: int = 1,
        target_width: int = 1,
    ) -> Witness:
        """Bind a witness to the exact IR snapshots a compiler will persist."""
        from qstack.compilation import module_text

        source_hash = sha256(module_text(source_module).encode("utf-8")).hexdigest()
        target_hash = sha256(module_text(target_module).encode("utf-8")).hexdigest()
        return cls(
            source_hash, target_hash, source_width, target_width,
            rules, claims, edges, kernels,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Witness:
        if not isinstance(data, dict):
            raise TypeError("witness must be a JSON object")
        return cls(
            str(data["source_sha256"]),
            str(data["target_sha256"]),
            int(data["source_width"]),
            int(data["target_width"]),
            tuple(Rule.from_dict(item) for item in data["rules"]),
            tuple(Claim.from_dict(item) for item in data["claims"]),
            tuple(Edge.from_dict(item) for item in data["edges"]),
            tuple(KernelBoundary.from_dict(item) for item in data["kernels"]),
        )
