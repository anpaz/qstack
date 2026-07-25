"""Registry for qstack ISA dialect operations."""

from __future__ import annotations

from xdsl.ir import Dialect
from xdsl.irdl import IRDLOperation

from qstack.dialect.atoms import Atoms
from qstack.dialect.cliffords import Cliffords
from qstack.dialect.h2 import H2
from qstack.dialect.toy import Toy


_DIALECTS: dict[str, Dialect] = {
    Atoms.name: Atoms,
    Toy.name: Toy,
    Cliffords.name: Cliffords,
    H2.name: H2,
}


def register_isa_dialect(dialect: Dialect) -> None:
    _DIALECTS[dialect.name] = dialect


def get_isa_dialect(name: str) -> Dialect:
    try:
        return _DIALECTS[name]
    except KeyError as exc:
        raise ValueError(f"unknown qstack ISA dialect {name!r}") from exc


def get_isa_op(isa_name: str, gate_name: str) -> type[IRDLOperation]:
    op_name = f"{isa_name}.{gate_name}"
    dialect = get_isa_dialect(isa_name)
    for op_type in dialect.operations:
        if op_type.name == op_name:
            return op_type
    raise ValueError(
        f"include declares gate {gate_name!r} for ISA {isa_name!r}, "
        f"but IR op {op_name!r} was not found"
    )

