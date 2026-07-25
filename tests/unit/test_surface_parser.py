"""Phase 3a tests: the lark grammar accepts the prepare_one surface."""

import pytest

from qstack_mlir.surface.parser import parse

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


def test_prepare_one_parses() -> None:
    tree = parse(PREPARE_ONE)
    assert tree is not None
    # Sanity: the tree contains the declarations we expect.
    rendered = tree.pretty()
    assert "selector_decl" in rendered
    assert "def_decl" in rendered
    assert "switch_stmt" in rendered
    assert "case_arm" in rendered


@pytest.mark.parametrize(
    "snippet",
    [
        # Just a header + extern.
        "QSTACKQASM 0.1;\nextern majority_vote(bit, bit, bit) -> bit;\n",
        # gate stmt with multi-qubit args
        "QSTACKQASM 0.1;\ndef f(qubit a, qubit b) { cx a, b; }\n",
        # measure with creg index
        "QSTACKQASM 0.1;\nqreg q[1]; creg c[1]; measure q[0] -> c[0];\n",
    ],
)
def test_smaller_snippets_parse(snippet: str) -> None:
    parse(snippet)


def test_invalid_program_errors() -> None:
    with pytest.raises(Exception):
        parse("this is not qasm")


def test_missing_header_errors() -> None:
    # The QSTACKQASM directive is mandatory; bare programs are rejected.
    with pytest.raises(Exception):
        parse("qreg q[1]; creg c[1]; measure q[0] -> c[0];\n")


def test_openqasm_header_is_rejected() -> None:
    # QSTACKQASM is intentionally not OpenQASM 3.0 — wrong directive must fail.
    with pytest.raises(Exception):
        parse("OPENQASM 3.0;\nqreg q[1];\n")
