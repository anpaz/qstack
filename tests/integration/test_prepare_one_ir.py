"""Phase 1 Verify: hand-built `prepare_one` IR matches DESIGN.md §2.1.

Constructs the entire `prepare_one` module programmatically and asserts
both: (a) it builds and round-trips clean through the xdsl text format,
(b) every novel op (kernel, measure, return, select, decode-not-yet,
cliffords.h, cliffords.cx) is present, (c) the surfaced select is wired
to the surfaced bit from the kernel via SSA.

Linearity / signature verification is Phase 1.1; this test only checks
structural well-formedness as far as xdsl itself cares.
"""

from io import StringIO

from xdsl.context import Context
from xdsl.dialects.builtin import Builtin, FunctionType, ModuleOp, SymbolRefAttr, UnitAttr
from xdsl.dialects.func import CallOp, Func, FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Block, Region
from xdsl.parser import Parser
from xdsl.printer import Printer

from qstack.dialect import BitType, QStack, QubitType
from qstack.dialect.cliffords import Cliffords, CxOp, HOp
from qstack.dialect.core import InvokeOp, KernelOp, MeasureOp, ReturnOp, SelectOp
from qstack.verifier import verify_module


def _ctx() -> Context:
    ctx = Context()
    ctx.load_dialect(Builtin)
    ctx.load_dialect(Func)
    ctx.load_dialect(QStack)
    ctx.load_dialect(Cliffords)
    return ctx


def _build_id() -> FuncOp:
    """func.func @id(%q: !qstack.qubit) -> !qstack.qubit { func.return %q }"""
    blk = Block(arg_types=[QubitType()])
    blk.add_op(FuncReturn.create(operands=[blk.args[0]]))
    return FuncOp("id", FunctionType.from_lists([QubitType()], [QubitType()]), Region([blk]))


def _build_selector_decl() -> FuncOp:
    """Body-less func.func private @repeat_until_one(%b: !qstack.bit)
    attributes { qstack.selector }."""
    fn = FuncOp.external(
        "repeat_until_one",
        [BitType()],
        [],
    )
    fn.attributes["qstack.selector"] = UnitAttr()
    return fn


def _build_prepare_one() -> FuncOp:
    """func.func @prepare_one(%q0: !qstack.qubit) -> !qstack.qubit { ... }"""
    outer = Block(arg_types=[QubitType()])
    q0 = outer.args[0]

    # qstack.kernel { ^bb0(%q1: qubit /*alloc*/): ... } : () -> (bit, qubit)
    # Block args are allocations only; %q0 is captured from the enclosing
    # function scope and threaded back as the trailing qubit result.
    kbody = Block(arg_types=[QubitType()])
    q1 = kbody.args[0]
    # %q0a = cliffords.h %q0   (captured from outer scope)
    ha = HOp(q0)
    kbody.add_op(ha)
    # %q0b, %q1a = cliffords.cx %q0a, %q1
    cx = CxOp(ha.result, q1)
    kbody.add_op(cx)
    # %meas = qstack.measure %q1a
    meas = MeasureOp(operand=cx.target_out)
    kbody.add_op(meas)
    # qstack.return %meas, %q0b
    kbody.add_op(ReturnOp(operands=[meas.result, cx.control_out]))

    kernel = KernelOp(
        result_types=[BitType(), QubitType()],
        region=Region([kbody]),
    )
    outer.add_op(kernel)
    m_bit, q0_inner = kernel.results

    # %cont = qstack.select @repeat_until_one(b = %m)
    #     continuations { done = @id, retry = @prepare_one }
    #     : (qubit) -> qubit
    cont_type = FunctionType.from_lists([QubitType()], [QubitType()])
    sel = SelectOp(
        callee=SymbolRefAttr("repeat_until_one"),
        bit_names=["b"],
        bit_operands=[m_bit],
        continuations={
            "done": SymbolRefAttr("id"),
            "retry": SymbolRefAttr("prepare_one"),
        },
        result_type=cont_type,
    )
    outer.add_op(sel)

    # %q0_out = qstack.invoke %cont(%q0_inner) : (qubit) -> qubit
    cii = InvokeOp(callee=sel.result, args=[q0_inner], result_types=[QubitType()])
    outer.add_op(cii)
    outer.add_op(FuncReturn.create(operands=[cii.results[0]]))

    return FuncOp(
        "prepare_one",
        FunctionType.from_lists([QubitType()], [QubitType()]),
        Region([outer]),
    )


def _build_main() -> FuncOp:
    """func.func @main() -> !qstack.bit { ... }"""
    outer = Block(arg_types=[])

    kbody = Block(arg_types=[QubitType()])
    q0 = kbody.args[0]
    # %q0_one = func.call @prepare_one(%q0) : (qubit) -> qubit
    call = CallOp("prepare_one", [q0], [QubitType()])
    kbody.add_op(call)
    # %m = qstack.measure %q0_one
    meas = MeasureOp(operand=call.results[0])
    kbody.add_op(meas)
    kbody.add_op(ReturnOp(operands=[meas.result]))

    kernel = KernelOp(result_types=[BitType()], region=Region([kbody]))
    outer.add_op(kernel)
    outer.add_op(FuncReturn.create(operands=[kernel.results[0]]))

    return FuncOp("main", FunctionType.from_lists([], [BitType()]), Region([outer]))


def _build_module() -> ModuleOp:
    return ModuleOp(
        [
            _build_id(),
            _build_selector_decl(),
            _build_prepare_one(),
            _build_main(),
        ]
    )


def test_prepare_one_builds() -> None:
    m = _build_module()
    # xdsl's structural verification (operand types, terminators, etc.)
    m.verify()


def test_prepare_one_passes_module_verifier() -> None:
    """The full prepare_one IR satisfies the qstack linearity + signature rules."""
    verify_module(_build_module())


def test_prepare_one_contains_all_expected_ops() -> None:
    m = _build_module()
    buf = StringIO()
    Printer(stream=buf).print_op(m)
    text = buf.getvalue()
    for sym in (
        "@id",
        "@prepare_one",
        "@main",
        "@repeat_until_one",
        "qstack.kernel",
        "qstack.measure",
        "qstack.return",
        "qstack.select",
        "cliffords.h",
        "cliffords.cx",
        "qstack.invoke",
        "func.call",
        "done",
        "retry",
    ):
        assert sym in text, f"missing {sym!r} in module:\n{text}"


def test_prepare_one_roundtrip() -> None:
    ctx = _ctx()
    m = _build_module()
    buf = StringIO()
    Printer(stream=buf).print_op(m)
    text = buf.getvalue()
    m2 = Parser(ctx, text).parse_module()
    buf2 = StringIO()
    Printer(stream=buf2).print_op(m2)
    assert buf2.getvalue() == text
