"""IPython cell magic for the qstack MLIR surface.

Usage in a notebook::

    %load_ext qstack.jupyter

    %%qasm
    QSTACKQASM 0.1;
    include "qstack/cliffords.inc";
    ...

The cell body is parsed by :mod:`qstack.surface.parser`, lowered to a
``ModuleOp`` via :mod:`qstack.surface.lowering`, verified, and bound
in the user namespace under the name given on the magic line (default
``module``). The cell's *display value* is the ``ModuleOp`` itself, so
Jupyter will render its textual IR.
"""

from __future__ import annotations

from IPython.core.magic import Magics, cell_magic, magics_class

from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module
from qstack.visualize import dataflow


@magics_class
class QStackMagics(Magics):
    @cell_magic
    def qasm(self, line: str, cell: str):
        var_name = line.strip() or "module"
        module = lower(parse(cell))
        verify_module(module)
        self.shell.user_ns[var_name] = module
        return module


def load_ipython_extension(ipython) -> None:
    ipython.register_magics(QStackMagics)
    ipython.user_ns.setdefault("dataflow", dataflow)
