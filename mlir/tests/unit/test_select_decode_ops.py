"""Phase 1c tests: qstack.select / qstack.decode.

Programmatic construction + generic round-trip. Symbol-presence and
signature-matching checks belong to the Phase 1.1 module-level verifier.
"""

from io import StringIO

from xdsl.context import Context
from xdsl.dialects.builtin import (
    Builtin,
    DictionaryAttr,
    FunctionType,
    ModuleOp,
    StringAttr,
    SymbolRefAttr,
)
from xdsl.dialects.func import Func
from xdsl.ir import Block, Region
from xdsl.parser import Parser
from xdsl.printer import Printer

from qstack_mlir.dialect import BitType, QStack, QubitType
from qstack_mlir.dialect.core import DecodeOp, SelectOp


def _ctx() -> Context:
    ctx = Context()
    ctx.load_dialect(Builtin)
    ctx.load_dialect(Func)
    ctx.load_dialect(QStack)
    return ctx


def _make_select_module() -> ModuleOp:
    """A bare select op inside a function whose only role is to host the bit
    operand. Symbols `@sel`, `@id`, `@retry` are *not* declared — that's a
    verifier concern, not an IRDL concern."""
    from xdsl.dialects.func import FuncOp, ReturnOp as FuncReturn

    # func.func @host(%b: !qstack.bit) -> () { ... }
    body_block = Block(arg_types=[BitType()])
    b = body_block.args[0]

    cont_type = FunctionType.from_lists([QubitType()], [QubitType()])
    sel = SelectOp(
        callee=SymbolRefAttr("sel"),
        bit_names=["b"],
        bit_operands=[b],
        continuations={
            "done": SymbolRefAttr("id"),
            "retry": SymbolRefAttr("retry"),
        },
        result_type=cont_type,
    )
    body_block.add_op(sel)
    body_block.add_op(FuncReturn.create(operands=[]))

    fn = FuncOp(
        "host",
        FunctionType.from_lists([BitType()], []),
        Region([body_block]),
    )
    return ModuleOp([fn])


def _make_decode_module() -> ModuleOp:
    from xdsl.dialects.func import FuncOp, ReturnOp as FuncReturn

    body_block = Block(arg_types=[BitType(), BitType(), BitType()])
    p1, p2, p3 = body_block.args
    dec = DecodeOp(
        callee=SymbolRefAttr("majority_vote"),
        bit_operands=[p1, p2, p3],
    )
    body_block.add_op(dec)
    body_block.add_op(FuncReturn.create(operands=[dec.result]))

    fn = FuncOp(
        "host",
        FunctionType.from_lists([BitType(), BitType(), BitType()], [BitType()]),
        Region([body_block]),
    )
    return ModuleOp([fn])


def test_select_construct_and_print() -> None:
    m = _make_select_module()
    buf = StringIO()
    Printer(stream=buf).print_op(m)
    text = buf.getvalue()
    assert "qstack.select" in text
    assert "@sel" in text
    assert "done" in text and "retry" in text
    assert "@id" in text and "@retry" in text


def test_select_roundtrip() -> None:
    ctx = _ctx()
    m = _make_select_module()
    buf = StringIO()
    Printer(stream=buf).print_op(m)
    text = buf.getvalue()
    m2 = Parser(ctx, text).parse_module()
    buf2 = StringIO()
    Printer(stream=buf2).print_op(m2)
    assert buf2.getvalue() == text


def test_select_continuations_is_dictionary() -> None:
    m = _make_select_module()
    sel = next(op for op in m.walk() if isinstance(op, SelectOp))
    assert isinstance(sel.continuations, DictionaryAttr)
    assert set(sel.continuations.data.keys()) == {"done", "retry"}


def test_select_bit_names_align_with_operands() -> None:
    m = _make_select_module()
    sel = next(op for op in m.walk() if isinstance(op, SelectOp))
    assert [s.data for s in sel.bit_names.data] == ["b"]
    assert len(list(sel.bit_operands)) == 1


def test_decode_construct_and_print() -> None:
    m = _make_decode_module()
    buf = StringIO()
    Printer(stream=buf).print_op(m)
    text = buf.getvalue()
    assert "qstack.decode" in text
    assert "@majority_vote" in text
    assert "!qstack.bit" in text


def test_decode_roundtrip() -> None:
    ctx = _ctx()
    m = _make_decode_module()
    buf = StringIO()
    Printer(stream=buf).print_op(m)
    text = buf.getvalue()
    m2 = Parser(ctx, text).parse_module()
    buf2 = StringIO()
    Printer(stream=buf2).print_op(m2)
    assert buf2.getvalue() == text


def test_decode_result_is_bit() -> None:
    m = _make_decode_module()
    dec = next(op for op in m.walk() if isinstance(op, DecodeOp))
    assert isinstance(dec.result.type, BitType)
