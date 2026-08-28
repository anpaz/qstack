"""Custom textual syntax is available for every qstack operation."""

from __future__ import annotations

from io import StringIO

from xdsl.context import Context
from xdsl.dialects.builtin import Builtin, ModuleOp, SymbolRefAttr
from xdsl.ir import Block, Region
from xdsl.parser import Parser
from xdsl.printer import Printer

from qstack.dialect.atoms import Atoms, CzOp as AtomsCzOp, RzOp as AtomsRzOp, SxOp
from qstack.dialect.cliffords import Cliffords, CxOp, CzOp, HOp, SOp, XOp, YOp, ZOp
from qstack.dialect.core import (
    BitType,
    CallOp,
    DecodeOp,
    DecoderOp,
    KernelOp,
    MeasureOp,
    QStack,
    QubitType,
    ReturnOp,
    SelectOp,
    SelectorOp,
)
from qstack.dialect.h2 import H2, RzOp as H2RzOp, RzzOp, U1Op, ZzOp
from qstack.dialect.toy import EntangleOp, FlipOp, MixOp, SkewOp, Toy
from qstack.verifier import verify_module


def _print(op: ModuleOp) -> str:
    stream = StringIO()
    Printer(stream=stream).print_op(op)
    return stream.getvalue()


def _parse(text: str, *dialects: object) -> ModuleOp:
    context = Context()
    context.load_dialect(Builtin)
    context.load_dialect(QStack)
    for dialect in dialects:
        context.load_dialect(dialect)  # type: ignore[arg-type]
    return Parser(context, text).parse_module()


def test_every_isa_gate_uses_compact_syntax_and_roundtrips() -> None:
    gates = (
        (Toy, lambda first, second: FlipOp(first)),
        (Toy, lambda first, second: MixOp(first)),
        (Toy, lambda first, second: SkewOp(first, 0.25)),
        (Toy, lambda first, second: EntangleOp(first, second)),
        (Cliffords, lambda first, second: HOp(first)),
        (Cliffords, lambda first, second: XOp(first)),
        (Cliffords, lambda first, second: YOp(first)),
        (Cliffords, lambda first, second: ZOp(first)),
        (Cliffords, lambda first, second: SOp(first)),
        (Cliffords, lambda first, second: CxOp(first, second)),
        (Cliffords, lambda first, second: CzOp(first, second)),
        (H2, lambda first, second: U1Op(first, 1.0, 2.0)),
        (H2, lambda first, second: H2RzOp(first, 1.0)),
        (H2, lambda first, second: RzzOp(first, second, 1.0)),
        (H2, lambda first, second: ZzOp(first, second)),
        (Atoms, lambda first, second: AtomsRzOp(first, 1.0)),
        (Atoms, lambda first, second: SxOp(first)),
        (Atoms, lambda first, second: AtomsCzOp(first, second)),
    )

    for dialect, build_gate in gates:
        block = Block(arg_types=[QubitType(), QubitType()])
        gate = build_gate(block.args[0], block.args[1])
        block.add_op(gate)
        module = ModuleOp(
            [
                KernelOp(
                    "main",
                    input_types=[QubitType(), QubitType()],
                    result_types=[],
                    allocates=0,
                    region=Region([block]),
                )
            ]
        )

        text = _print(module)
        assert f'"{gate.name}"' not in text
        _parse(text, dialect)


def test_core_symbols_and_control_ops_use_compact_syntax_and_roundtrip() -> None:
    worker_block = Block(arg_types=[QubitType()])
    mixed = MixOp(worker_block.args[0])
    worker_block.add_op(mixed)
    worker_block.add_op(ReturnOp(operands=[mixed.result]))
    worker = KernelOp(
        "worker",
        input_types=[QubitType()],
        result_types=[QubitType()],
        allocates=0,
        region=Region([worker_block]),
    )

    case_block = Block(arg_types=[QubitType()])
    case_block.add_op(ReturnOp(operands=[case_block.args[0]]))
    case = KernelOp(
        "case_one",
        input_types=[QubitType()],
        result_types=[QubitType()],
        allocates=0,
        region=Region([case_block]),
    )

    main_block = Block(arg_types=[QubitType(), QubitType()])
    call = CallOp("worker", [main_block.args[0]], [QubitType()])
    main_block.add_op(call)
    first_measurement = MeasureOp(operand=call.results[0])
    main_block.add_op(first_measurement)
    decoded = DecodeOp(callee="decode", bit_operands=[first_measurement.result])
    main_block.add_op(decoded)
    selected = SelectOp(
        callee="choose",
        bit_operands=[decoded.result],
        cases={"one": SymbolRefAttr("case_one")},
        case_arguments=[main_block.args[1]],
        result_types=[QubitType()],
    )
    main_block.add_op(selected)
    second_measurement = MeasureOp(operand=selected.results[0])
    main_block.add_op(second_measurement)
    main_block.add_op(ReturnOp(operands=[second_measurement.result]))
    main = KernelOp(
        "main",
        input_types=[],
        result_types=[BitType()],
        allocates=2,
        region=Region([main_block]),
    )

    module = ModuleOp(
        [
            SelectorOp("choose", 1),
            DecoderOp("decode", 1),
            worker,
            case,
            main,
        ]
    )
    text = _print(module)
    for name in (
        "qstack.kernel",
        "qstack.selector",
        "qstack.decoder",
        "qstack.call",
        "qstack.decode",
        "qstack.select",
        "qstack.measure",
        "qstack.return",
    ):
        assert f'"{name}"' not in text
    assert "qstack.kernel @main" in text
    assert "allocates 2" in text
    assert "#builtin.int<2>" not in text
    assert "qstack.selector @choose arity 1" in text
    assert "qstack.decoder @decode arity 1" in text

    reparsed = _parse(text, Toy)
    verify_module(reparsed)

    cloned = reparsed.clone()
    verify_module(cloned)
    cloned_main = next(op for op in cloned.body.ops if isinstance(op, KernelOp) and op.sym_name.data == "main")
    assert tuple(cloned_main.result_types) == ()
    assert cloned_main.declared_result_types == (BitType(),)
