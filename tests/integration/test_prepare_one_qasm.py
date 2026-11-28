"""Phase 3b tests: lower the parsed surface tree to a qstack ModuleOp."""

import shutil

import pytest
from xdsl.dialects.builtin import ModuleOp

from qstack.dialect import BitType, QubitType
from qstack.dialect.core import KernelOp, SelectorOp
from qstack.passes.rep3_bit import lower_rep3_bit
from qstack.runtime import CallbackRegistry
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.validation import validate_module
from qstack.verification import generate_docket, verify

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


def _module(src: str) -> ModuleOp:
    return lower(parse(src))


def test_prepare_one_lowers_to_expected_symbols() -> None:
    m = _module(PREPARE_ONE)
    syms = {op.sym_name.data: op for op in m.body.ops if hasattr(op, "sym_name")}
    # extern selector + def + main + auto-generated case continuations
    assert "repeat_until_one" in syms
    assert "prepare_one" in syms
    assert "main" in syms

    # repeat_until_one is a top-level opaque selector declaration.
    sel = syms["repeat_until_one"]
    assert isinstance(sel, SelectorOp)

    # prepare_one signature: (qubit) -> qubit
    prep = syms["prepare_one"]
    assert isinstance(prep, KernelOp)
    assert [type(t) for t in prep.input_types] == [QubitType]
    assert [type(t) for t in prep.declared_result_types] == [QubitType]

    # main signature: () -> bit
    main = syms["main"]
    assert isinstance(main, KernelOp)
    assert list(main.input_types) == []
    assert [type(t) for t in main.declared_result_types] == [BitType]


def test_prepare_one_passes_verifier() -> None:
    m = _module(PREPARE_ONE)
    validate_module(m)


def test_rep3_witness_covers_widened_recursive_selector() -> None:
    result = lower_rep3_bit(_module(PREPARE_ONE), CallbackRegistry())
    assert result.witness is not None
    (selector_rule,) = (rule for rule in result.witness.rules if rule.source.operations[0].name == "qstack.select")
    assert selector_rule.kind == "widening"
    report = verify(result, backends=())
    assert report.status == "UNSUPPORTED"
    assert report.kernels and all(kernel.status == "VERIFIED" for kernel in report.kernels)


@pytest.mark.skipif(shutil.which("dot") is None, reason="HTML graph export uses Graphviz")
def test_docket_names_selectors_and_called_kernels(tmp_path) -> None:
    result = lower_rep3_bit(_module(PREPARE_ONE), CallbackRegistry())
    output = tmp_path / "docket.html"
    generate_docket(result, output, witness_only=True)
    html = output.read_text()

    for name in ("select @repeat_until_one", "call @prepare_one"):
        label = f"{name} → {name}"
        assert f">{label}</text>" in html
        assert f"<h2>{label}</h2>" in html


def test_prepare_one_runs_1000_shots_all_one() -> None:
    from qstack.runtime import Machine

    reg = CallbackRegistry()

    @reg.selector("repeat_until_one")
    def _pick(bits):
        # continuation labels mirror the surface `case N:` numbers.
        return "0" if bits[0] == 1 else "1"  # 0 = done, 1 = retry

    m = _module(PREPARE_ONE)
    machine = Machine(num_qubits=4, registry=reg)
    results = machine.eval(m, shots=1000)
    assert all(r == [1] for r in results)
