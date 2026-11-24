"""Phase 3a tests: the lark grammar accepts the prepare_one surface."""

import pytest

from qstack.surface.parser import parse

PREPARE_ONE = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

extern selector repeat_until_one(bit) -> int;

def prepare_one(qubit q) {
  qubit[1] ancilla;
  bit m;
  h q;
  cx q, ancilla[0];
  measure ancilla[0] -> m;
  switch (repeat_until_one(m)) {
    case 0 { }
    case 1 { prepare_one(q); }
  }
}

qubit[1] q;
bit[1] c;
prepare_one(q[0]);
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
        # measure with a bit register index
        "QSTACKQASM 0.1;\nqreg q[1]; bit[1] c; measure q[0] -> c[0];\n",
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
        parse("qubit[1] q; bit[1] c; measure q[0] -> c[0];\n")


def test_openqasm_header_is_rejected() -> None:
    # QSTACKQASM is intentionally not OpenQASM 3.0 — wrong directive must fail.
    with pytest.raises(Exception):
        parse("OPENQASM 3.0;\nqreg q[1];\n")


@pytest.mark.parametrize(
    "snippet",
    [
        "QSTACKQASM 0.1;\nextern selector s(bit) -> int;\nqreg q[1]; bit m; measure q[0] -> m;\n"
        "while (s(m)) { measure q[0] -> m; }\n",
        "QSTACKQASM 0.1;\nqreg q[3]; for int i in [0:2] { x q[i]; }\n",
        "QSTACKQASM 0.1;\nqreg q[3]; for uint[8] i in [0:2:2] { x q[i]; }\n",
        "QSTACKQASM 0.1;\nqreg q[3]; for int i in {0, 2} { x q[i]; }\n",
        "QSTACKQASM 0.1;\nextern maj(bit, bit, bit) -> bit;\nbit b = maj(c[0], c[1], c[2]);\n",
        "QSTACKQASM 0.1;\nextern maj(bit, bit, bit) -> bit;\nb = maj(c[0], c[1], c[2]);\n",
    ],
)
def test_new_statements_parse(snippet: str) -> None:
    parse(snippet)


def test_a_case_label_takes_no_colon() -> None:
    head = "QSTACKQASM 0.1;\nextern selector s(bit) -> int;\nbit m;\n"
    parse(head + "switch (s(m)) { case 0 { } }\n")
    with pytest.raises(Exception):
        parse(head + "switch (s(m)) { case 0: { } }\n")
