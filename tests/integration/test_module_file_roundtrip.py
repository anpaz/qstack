"""Persist qstack MLIR to disk, reload it, and execute the reloaded module."""

from pathlib import Path

from xdsl.context import Context
from xdsl.dialects.builtin import Builtin
from xdsl.dialects.func import Func
from xdsl.parser import Parser
from xdsl.printer import Printer

from qstack.dialect import QStack
from qstack.dialect.atoms import Atoms
from qstack.runtime import Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse


def _ctx() -> Context:
    context = Context()
    context.load_dialect(Builtin)
    context.load_dialect(Func)
    context.load_dialect(QStack)
    context.load_dialect(Atoms)
    return context


def test_module_file_roundtrip_then_execute(tmp_path: Path) -> None:
    module = lower(
        parse(
            """
QSTACKQASM 0.1;
include "qstack/atoms.inc";

qreg q[1];
creg c[1];
sx q[0];
sx q[0];
measure q[0] -> c[0];
"""
        )
    )

    path = tmp_path / "sx_squared.mlir"
    with path.open("w") as stream:
        Printer(stream=stream).print_op(module)

    reloaded = Parser(_ctx(), path.read_text()).parse_module()

    results = Machine(reloaded, num_qubits=1).eval(shots=10)
    assert all(result == [1] for result in results)

