"""Phase 3b tests: lower the parsed surface tree to a qstack ModuleOp."""

from xdsl.dialects.builtin import ModuleOp

from qstack.dialect import BitType, QubitType
from qstack.dialect.core import KernelOp, SelectorOp
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module

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
    verify_module(m)


def test_prepare_one_runs_1000_shots_all_one() -> None:
    from qstack.runtime import CallbackRegistry, Machine

    reg = CallbackRegistry()

    @reg.selector("repeat_until_one")
    def _pick(bits):
        # continuation labels mirror the surface `case N:` numbers.
        return "0" if bits[0] == 1 else "1"  # 0 = done, 1 = retry

    m = _module(PREPARE_ONE)
    machine = Machine(m, num_qubits=4, registry=reg)
    results = machine.eval(shots=1000)
    assert all(r == [1] for r in results)
