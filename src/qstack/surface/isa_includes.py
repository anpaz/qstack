"""Resolution of QSTACKQASM ISA include files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from lark import Token, Tree
from xdsl.irdl import IRDLOperation

from qstack.dialect.registry import get_isa_op


_INCLUDE_DIR = Path(__file__).with_name("includes")
_PRAGMA_RE = re.compile(r"#pragma\s+qstack\.isa\s+([A-Za-z_][A-Za-z0-9_]*)\s*;")
_GATE_RE = re.compile(
    r"\bgate\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(([^)]*)\))?\s+([^;]+);"
)


@dataclass(frozen=True)
class GateDecl:
    name: str
    isa: str
    include_path: str
    op_type: type[IRDLOperation]
    params: tuple[str, ...]
    qubits: tuple[str, ...]

    @property
    def arity(self) -> int:
        return len(self.qubits)


@dataclass(frozen=True)
class ISAInclude:
    path: str
    isa: str
    gates: dict[str, GateDecl]


@dataclass(frozen=True)
class IncludeGateSet:
    includes: tuple[ISAInclude, ...]
    gates: dict[str, GateDecl]


def resolve_includes(include_nodes: list[Tree]) -> IncludeGateSet:
    includes: list[ISAInclude] = []
    gates: dict[str, GateDecl] = {}
    for node in include_nodes:
        include_path = _include_path(node)
        text = _read_include(include_path)
        parsed = _parse_include(include_path, text)
        if parsed is None:
            continue
        _validate_include(parsed)
        for name, gate in parsed.gates.items():
            previous = gates.get(name)
            if previous is not None:
                raise ValueError(
                    f"gate {name!r} is declared by multiple ISA includes: "
                    f"{previous.include_path!r} ({previous.isa}) and "
                    f"{gate.include_path!r} ({gate.isa})"
                )
            gates[name] = gate
        includes.append(parsed)
    return IncludeGateSet(includes=tuple(includes), gates=gates)


def _include_path(node: Tree) -> str:
    if node.data != "include":
        raise TypeError(f"expected include tree, got {node.data!r}")
    token = node.children[0]
    if not isinstance(token, Token):
        raise TypeError(f"expected include path token, got {token!r}")
    return str(token)[1:-1]


def _read_include(include_path: str) -> str:
    if not include_path.startswith("qstack/"):
        raise ValueError(f"unsupported include path {include_path!r}")
    local = include_path.removeprefix("qstack/")
    path = _INCLUDE_DIR / local
    if not path.is_file():
        raise FileNotFoundError(f"include file {include_path!r} not found")
    return path.read_text()


def _parse_include(include_path: str, text: str) -> ISAInclude | None:
    pragma = _PRAGMA_RE.search(text)
    if pragma is None:
        return None
    isa = pragma.group(1)
    gates: dict[str, GateDecl] = {}
    for match in _GATE_RE.finditer(text):
        name = match.group(1)
        params = _split_names(match.group(2) or "")
        qubits = _split_names(match.group(3))
        if name in gates:
            raise ValueError(f"include {include_path!r} declares gate {name!r} more than once")
        op_type = get_isa_op(isa, name)
        gates[name] = GateDecl(
            name=name,
            isa=isa,
            include_path=include_path,
            op_type=op_type,
            params=params,
            qubits=qubits,
        )
    return ISAInclude(path=include_path, isa=isa, gates=gates)


def _split_names(source: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in source.split(",") if part.strip())


def _validate_include(include: ISAInclude) -> None:
    for gate in include.gates.values():
        definition = gate.op_type.get_irdl_definition()
        properties = tuple(definition.properties)
        if properties != gate.params:
            raise ValueError(
                f"include {include.path!r} declares gate {gate.name!r} "
                f"with params {gate.params}, but op {gate.op_type.name!r} has "
                f"properties {properties}"
            )
        if len(definition.operands) != gate.arity or len(definition.results) != gate.arity:
            raise ValueError(
                f"include {include.path!r} declares gate {gate.name!r} "
                f"with {gate.arity} qubits, but op {gate.op_type.name!r} has "
                f"{len(definition.operands)} operands and {len(definition.results)} results"
            )
        for _, operand in definition.operands:
            if not _is_qubit_constraint(operand.constr):
                raise ValueError(f"op {gate.op_type.name!r} has a non-qubit operand")
        for _, result in definition.results:
            if not _is_qubit_constraint(result.constr):
                raise ValueError(f"op {gate.op_type.name!r} has a non-qubit result")


def _is_qubit_constraint(constr: object) -> bool:
    return "QubitType" in repr(constr)
