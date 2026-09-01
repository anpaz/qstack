"""Tests for the IPython ``%%qasm`` cell magic."""

import pytest

pytest.importorskip("IPython")

from IPython.testing.globalipapp import start_ipython  # noqa: E402
from IPython.core.getipython import get_ipython  # noqa: E402
from xdsl.dialects.builtin import ModuleOp  # noqa: E402

from qstack.jupyter import load_ipython_extension  # noqa: E402
from qstack.visualize import dataflow  # noqa: E402

PREPARE_ONE = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

extern selector repeat_until_one(bit) -> int;

def prepare_one(qubit q) {
  qreg ancilla[1];
  bit m;
  h q;
  cx q, ancilla[0];
  measure ancilla[0] -> m;
  switch (repeat_until_one(m)) {
    case 0: { }
    case 1: { prepare_one q; }
  }
}

qreg q[1];
creg c[1];
prepare_one q[0];
measure q[0] -> c[0];
"""


@pytest.fixture
def ip():
    shell = get_ipython()
    if shell is None:
        start_ipython()
        shell = get_ipython()
    shell.user_ns.clear()
    load_ipython_extension(shell)
    return shell


def test_qasm_magic_binds_module_in_user_namespace(ip) -> None:
    ip.run_cell_magic("qasm", "", PREPARE_ONE)
    assert "module" in ip.user_ns
    assert isinstance(ip.user_ns["module"], ModuleOp)


def test_qasm_magic_binds_under_custom_name(ip) -> None:
    ip.run_cell_magic("qasm", "mymod", PREPARE_ONE)
    assert isinstance(ip.user_ns["mymod"], ModuleOp)
    assert "module" not in ip.user_ns


def test_qasm_magic_returns_module(ip) -> None:
    result = ip.run_cell_magic("qasm", "", PREPARE_ONE)
    assert isinstance(result, ModuleOp)


def test_extension_exposes_dataflow_helper(ip) -> None:
    assert ip.user_ns["dataflow"] is dataflow
