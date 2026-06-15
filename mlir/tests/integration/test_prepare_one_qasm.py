"""Phase 3b tests: lower the parsed surface tree to a qstack ModuleOp."""

from xdsl.dialects.builtin import FunctionType, ModuleOp
from xdsl.dialects.func import FuncOp

from qstack_mlir.dialect import BitType, QubitType
from qstack_mlir.surface.lowering import lower
from qstack_mlir.surface.parser import parse
from qstack_mlir.verifier import verify_module

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
    syms: dict[str, FuncOp] = {op.sym_name.data: op for op in m.body.ops if isinstance(op, FuncOp)}
    # extern selector + def + main + auto-generated case continuations
    assert "repeat_until_one" in syms
    assert "prepare_one" in syms
    assert "main" in syms

    # repeat_until_one is body-less and selector-tagged.
    sel = syms["repeat_until_one"]
    assert sel.is_declaration
    assert "qstack.selector" in sel.attributes

    # prepare_one signature: (qubit) -> qubit
    prep_ty = syms["prepare_one"].function_type
    assert [type(t) for t in prep_ty.inputs.data] == [QubitType]
    assert [type(t) for t in prep_ty.outputs.data] == [QubitType]

    # main signature: () -> bit
    main_ty = syms["main"].function_type
    assert list(main_ty.inputs.data) == []
    assert [type(t) for t in main_ty.outputs.data] == [BitType]


def test_prepare_one_passes_verifier() -> None:
    m = _module(PREPARE_ONE)
    verify_module(m)


def test_prepare_one_runs_1000_shots_all_one() -> None:
    from qstack_mlir.runtime import CallbackRegistry, Machine

    reg = CallbackRegistry()

    @reg.selector("repeat_until_one")
    def _pick(*, b0):
        # continuation labels mirror the surface `case N:` numbers.
        return "0" if b0 == 1 else "1"  # 0 = done, 1 = retry

    m = _module(PREPARE_ONE)
    machine = Machine(m, num_qubits=4, registry=reg)
    results = machine.shots("main", 1000)
    assert all(r == [1] for r in results)
