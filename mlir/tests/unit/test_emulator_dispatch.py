"""Phase 2c tests: cross-function dispatch in the emulator.

Covers:

* ``func.call`` into another ``func.func`` and ``func.return`` back.
* ``qstack.select`` invoking a Python selector and yielding a continuation
  handle as an SSA value of MLIR function type.
* ``qstack.invoke`` consuming that handle and calling the continuation.
* ``qstack.decode`` invoking a Python decoder on a bundle of bits.
"""

from xdsl.dialects.builtin import FunctionType, ModuleOp, SymbolRefAttr, UnitAttr
from xdsl.dialects.func import CallOp, FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Block, Region

from qstack_mlir.dialect import BitType, QubitType
from qstack_mlir.dialect.cliffords import HOp, XOp
from qstack_mlir.dialect.core import (
    DecodeOp,
    InvokeOp,
    KernelOp,
    MeasureOp,
    ReturnOp,
    SelectOp,
)
from qstack_mlir.runtime import CallbackRegistry
from qstack_mlir.runtime.emulator import Emulator


def test_func_call_runs_callee_body() -> None:
    """@main allocates and calls @flip, which X's the qubit and returns it.
    @main then measures — expect 1."""
    # @flip(%q) -> qubit { %q' = X %q ; return %q' }
    fblk = Block(arg_types=[QubitType()])
    x = XOp(fblk.args[0])
    fblk.add_op(x)
    fblk.add_op(FuncReturn.create(operands=[x.result]))
    flip = FuncOp("flip", FunctionType.from_lists([QubitType()], [QubitType()]), Region([fblk]))

    # @main() -> bit { %b = kernel { ^bb(%q): %q2 = call @flip(%q) ; meas ; ret } ; ret }
    mainouter = Block(arg_types=[])
    kbody = Block(arg_types=[QubitType()])
    call = CallOp("flip", [kbody.args[0]], [QubitType()])
    kbody.add_op(call)
    meas = MeasureOp(operand=call.results[0])
    kbody.add_op(meas)
    kbody.add_op(ReturnOp(operands=[meas.result]))
    kernel = KernelOp(result_types=[BitType()], region=Region([kbody]))
    mainouter.add_op(kernel)
    mainouter.add_op(FuncReturn.create(operands=[kernel.results[0]]))
    main = FuncOp("main", FunctionType.from_lists([], [BitType()]), Region([mainouter]))

    module = ModuleOp([flip, main])
    emu = Emulator(num_qubits=4, module=module)
    for _ in range(20):
        assert emu.run_func("main") == [1]


def _build_decode_module(reg: CallbackRegistry) -> ModuleOp:
    """@main returns majority_vote(1, 1, 0) via qstack.decode."""

    @reg.decoder("majority_vote")
    def _maj(a, b, c):
        return 1 if (a + b + c) >= 2 else 0

    # decl
    decl = FuncOp.external("majority_vote", [BitType(), BitType(), BitType()], [BitType()])
    decl.attributes["qstack.decoder"] = UnitAttr()

    # @main: kernel allocates 3 qubits, X's first two, measures all,
    # decode -> bit
    outer = Block(arg_types=[])
    kbody = Block(arg_types=[QubitType(), QubitType(), QubitType()])
    q0, q1, q2 = kbody.args
    x0 = XOp(q0)
    kbody.add_op(x0)
    x1 = XOp(q1)
    kbody.add_op(x1)
    m0 = MeasureOp(operand=x0.result)
    kbody.add_op(m0)
    m1 = MeasureOp(operand=x1.result)
    kbody.add_op(m1)
    m2 = MeasureOp(operand=q2)
    kbody.add_op(m2)
    kbody.add_op(ReturnOp(operands=[m0.result, m1.result, m2.result]))
    kernel = KernelOp(result_types=[BitType(), BitType(), BitType()], region=Region([kbody]))
    outer.add_op(kernel)
    b0, b1, b2 = kernel.results
    decode = DecodeOp(
        callee=SymbolRefAttr("majority_vote"),
        bit_operands=[b0, b1, b2],
    )
    outer.add_op(decode)
    outer.add_op(FuncReturn.create(operands=[decode.result]))
    main = FuncOp("main", FunctionType.from_lists([], [BitType()]), Region([outer]))

    return ModuleOp([decl, main])


def test_decode_invokes_python_decoder() -> None:
    reg = CallbackRegistry()
    module = _build_decode_module(reg)
    emu = Emulator(num_qubits=4, module=module, registry=reg)
    for _ in range(10):
        assert emu.run_func("main") == [1]


def _build_select_invoke_module(reg: CallbackRegistry) -> ModuleOp:
    """Two continuations @id and @flip_q; @main prepares a bit (always 1
    via X+measure), selector picks @flip; invoke then X's the captured
    qubit; main measures the final qubit. Expect always 1."""

    @reg.selector("pick")
    def _pick(*, b):
        return "flip" if b == 1 else "id"

    # @id(q) -> q { ret q }
    idblk = Block(arg_types=[QubitType()])
    idblk.add_op(FuncReturn.create(operands=[idblk.args[0]]))
    id_fn = FuncOp("id", FunctionType.from_lists([QubitType()], [QubitType()]), Region([idblk]))

    # @flip_q(q) -> q { q' = X q ; ret q' }
    fblk = Block(arg_types=[QubitType()])
    fx = XOp(fblk.args[0])
    fblk.add_op(fx)
    fblk.add_op(FuncReturn.create(operands=[fx.result]))
    flip_fn = FuncOp("flip_q", FunctionType.from_lists([QubitType()], [QubitType()]), Region([fblk]))

    # selector decl
    sel_decl = FuncOp.external("pick", [BitType()], [])
    sel_decl.attributes["qstack.selector"] = UnitAttr()

    # @main: kernel { alloc q0,q1 ; X q0 ; b = meas q0 ; cont = select pick(b=b) {id|flip_q} ; q1' = invoke cont(q1) ; b1 = meas q1' ; ret b1 }
    outer = Block(arg_types=[])
    kbody = Block(arg_types=[QubitType(), QubitType()])
    q0, q1 = kbody.args
    x0 = XOp(q0)
    kbody.add_op(x0)
    m0 = MeasureOp(operand=x0.result)
    kbody.add_op(m0)
    cont_type = FunctionType.from_lists([QubitType()], [QubitType()])
    sel = SelectOp(
        callee=SymbolRefAttr("pick"),
        bit_names=["b"],
        bit_operands=[m0.result],
        continuations={"id": SymbolRefAttr("id"), "flip": SymbolRefAttr("flip_q")},
        result_type=cont_type,
    )
    kbody.add_op(sel)
    inv = InvokeOp(callee=sel.result, args=[q1], result_types=[QubitType()])
    kbody.add_op(inv)
    m1 = MeasureOp(operand=inv.results[0])
    kbody.add_op(m1)
    kbody.add_op(ReturnOp(operands=[m1.result]))
    kernel = KernelOp(result_types=[BitType()], region=Region([kbody]))
    outer.add_op(kernel)
    outer.add_op(FuncReturn.create(operands=[kernel.results[0]]))
    main = FuncOp("main", FunctionType.from_lists([], [BitType()]), Region([outer]))

    return ModuleOp([id_fn, flip_fn, sel_decl, main])


def test_select_invoke_routes_through_python_selector() -> None:
    reg = CallbackRegistry()
    module = _build_select_invoke_module(reg)
    emu = Emulator(num_qubits=4, module=module, registry=reg)
    for _ in range(20):
        assert emu.run_func("main") == [1]
