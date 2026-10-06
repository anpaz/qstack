"""IPython cell magic for the qstack MLIR surface.

Usage in a notebook::

    %load_ext qstack.jupyter

    %%qasm
    QSTACKQASM 0.1;
    include "qstack/cliffords.inc";
    ...

The cell body is parsed by :mod:`qstack.surface.parser`, lowered to a
``CompilationResult`` via :mod:`qstack.surface`, verified structurally, and bound
in the user namespace under the name given on the magic line (default
``module``). The result's ``.module`` holds the textual IR.
"""

from __future__ import annotations

from IPython.core.magic import Magics, cell_magic, magics_class

from qstack.surface import compile_qasm
from qstack.visualize import dataflow


@magics_class
class QStackMagics(Magics):
    @cell_magic
    def qasm(self, line: str, cell: str):
        var_name = line.strip() or "module"
        result = compile_qasm(cell)
        self.shell.user_ns[var_name] = result
        return result


def load_ipython_extension(ipython) -> None:
    ipython.register_magics(QStackMagics)
    ipython.user_ns.setdefault("dataflow", dataflow)
