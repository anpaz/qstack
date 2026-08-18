"""Tests for the phase-flip repetition-3 compiler pass."""

import pytest
from xdsl.dialects.builtin import FunctionType, ModuleOp, UnitAttr
from xdsl.dialects.func import FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, ZOp
from qstack.dialect.core import DecodeOp, KernelOp, MeasureOp
from qstack.passes.rep3_bit import compile_rep3_bit
from qstack.passes.rep3_phase import (
    Rep3PhaseCompileError,
    compile_rep3_phase,
    register_rep3_phase_callbacks,
)
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module
from tests.integration.test_prepare_one_qasm import PREPARE_ONE

PHASE_X_PROGRAM = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
x q[0];
measure q[0] -> c[0];
"""

PHASE_H_PROGRAM = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
h q[0];
measure q[0] -> c[0];
"""

CX_PROGRAM = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[2];
creg c[2];
cx q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""

UNSUPPORTED_Z_PROGRAM = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
z q[0];
measure q[0] -> c[0];
"""


def _module(src: str) -> ModuleOp:
    return lower(parse(src))


def _walk(module, op_type):
    return [op for op in module.walk() if isinstance(op, op_type)]


def _symbols(module: ModuleOp) -> dict[str, FuncOp]:
    return {
        op.sym_name.data: op
        for op in module.body.ops
        if isinstance(op, FuncOp)
    }


def test_rep3_phase_expands_main_signature_and_prepares_allocated_zero() -> None:
    out = compile_rep3_phase(_module(PHASE_X_PROGRAM))
    main = _symbols(out)["main"]
    kernel = next(op for op in main.body.block.ops if isinstance(op, KernelOp))

    assert [type(t) for t in main.function_type.outputs.data] == [BitType]
    assert len(kernel.body.block.args) == 3
    # Three allocation-preparation H gates and three measurement-basis H gates.
    assert len(_walk(kernel, HOp)) == 6


def test_rep3_phase_lowers_x_to_physical_z() -> None:
    out = compile_rep3_phase(_module(PHASE_X_PROGRAM))
    assert len(_walk(out, XOp)) == 0
    assert len(_walk(out, ZOp)) == 3
    verify_module(out)


def test_rep3_phase_measures_in_phase_basis_and_decodes() -> None:
    out = compile_rep3_phase(_module(PHASE_X_PROGRAM))
    assert len(_walk(out, MeasureOp)) == 3

    decodes = _walk(out, DecodeOp)
    assert len(decodes) == 1
    assert decodes[0].callee.root_reference.data == "phase_majority_vote"
    assert len(list(decodes[0].bit_operands)) == 3


def test_rep3_phase_lowers_h_gadget() -> None:
    out = compile_rep3_phase(_module(PHASE_H_PROGRAM))
    # Three preparation H gates, one logical-H gadget H, and three measurement H gates.
    assert len(_walk(out, HOp)) == 7
    assert len(_walk(out, CzOp)) == 2
    verify_module(out)


def test_rep3_phase_h_gadget_swaps_lane_mapping() -> None:
    body = Block(arg_types=[QubitType()])
    h = HOp(body.args[0])
    body.add_op(h)
    body.add_op(FuncReturn.create(operands=[h.result]))
    source = ModuleOp(
        [
            FuncOp(
                "main",
                FunctionType.from_lists([QubitType()], [QubitType()]),
                Region([body]),
            )
        ]
    )

    out = compile_rep3_phase(source)
    main = _symbols(out)["main"]
    h_op = _walk(main, HOp)[0]
    cz01, cz02 = _walk(main, CzOp)
    ret = next(op for op in main.body.block.ops if isinstance(op, FuncReturn))

    assert cz01.control is h_op.result
    assert cz02.control is cz01.control_out
    assert list(ret.arguments) == [
        cz02.target_out,
        cz01.target_out,
        cz02.control_out,
    ]


def test_rep3_phase_lowers_cx_transversally() -> None:
    out = compile_rep3_phase(_module(CX_PROGRAM))
    assert len(_walk(out, CxOp)) == 3
    assert len(_walk(out, MeasureOp)) == 6
    verify_module(out)


def test_rep3_phase_preserves_callbacks_and_continuations() -> None:
    source = _module(PREPARE_ONE)
    out = compile_rep3_phase(source)
    symbols = _symbols(out)

    selector = symbols["repeat_until_one"]
    assert selector.is_declaration
    assert "qstack.selector" in selector.attributes
    assert selector.function_type == _symbols(source)["repeat_until_one"].function_type
    assert [type(t) for t in symbols["prepare_one"].function_type.inputs.data] == [
        QubitType
    ] * 3
    assert [type(t) for t in symbols["prepare_one"].function_type.outputs.data] == [
        QubitType
    ] * 3


def test_rep3_phase_does_not_mutate_source_module() -> None:
    source = _module(PHASE_X_PROGRAM)
    out = compile_rep3_phase(source)

    assert out is not source
    assert len(_walk(source, XOp)) == 1
    assert len(_walk(source, MeasureOp)) == 1
    verify_module(source)
    verify_module(out)


def test_rep3_phase_adds_one_phase_majority_vote_declaration() -> None:
    out = compile_rep3_phase(_module(PHASE_X_PROGRAM))
    declarations = [
        op
        for op in out.body.ops
        if isinstance(op, FuncOp) and op.sym_name.data == "phase_majority_vote"
    ]
    assert len(declarations) == 1
    declaration = declarations[0]
    assert declaration.is_declaration
    assert "qstack.decoder" in declaration.attributes
    assert [type(t) for t in declaration.function_type.inputs.data] == [BitType] * 3
    assert [type(t) for t in declaration.function_type.outputs.data] == [BitType]


def test_rep3_phase_rejects_incompatible_phase_majority_vote_symbol() -> None:
    source = _module(PHASE_X_PROGRAM)
    source.body.block.add_op(
        FuncOp.external(
            "phase_majority_vote",
            [BitType()],
            [BitType()],
        )
    )
    with pytest.raises(Rep3PhaseCompileError, match="already exists"):
        compile_rep3_phase(source)


def test_rep3_phase_rejects_unsupported_gates() -> None:
    with pytest.raises(Rep3PhaseCompileError, match="unsupported Clifford"):
        compile_rep3_phase(_module(UNSUPPORTED_Z_PROGRAM))

    body = Block(arg_types=[QubitType()])
    s = SOp(body.args[0])
    body.add_op(s)
    body.add_op(FuncReturn.create(operands=[s.result]))
    source = ModuleOp(
        [
            FuncOp(
                "main",
                FunctionType.from_lists([QubitType()], [QubitType()]),
                Region([body]),
            )
        ]
    )
    with pytest.raises(Rep3PhaseCompileError, match="unsupported Clifford"):
        compile_rep3_phase(source)


def test_rep3_bit_plus_phase_composes_as_nine_wire_encoding() -> None:
    out = compile_rep3_phase(compile_rep3_bit(_module(PHASE_X_PROGRAM)))
    verify_module(out)

    kernel = next(op for op in _symbols(out)["main"].body.block.ops if isinstance(op, KernelOp))
    symbols = _symbols(out)
    decoders = _walk(out, DecodeOp)

    assert len(kernel.body.block.args) == 9
    assert "majority_vote" in symbols
    assert "phase_majority_vote" in symbols
    assert len([op for op in decoders if op.callee.root_reference.data == "phase_majority_vote"]) == 3
    assert len([op for op in decoders if op.callee.root_reference.data == "majority_vote"]) == 1


def test_rep3_bit_plus_phase_executes_deterministic_x_program() -> None:
    from qstack.passes.rep3_bit import register_rep3_bit_callbacks
    from qstack.runtime import CallbackRegistry, Machine

    out = compile_rep3_phase(compile_rep3_bit(_module(PHASE_X_PROGRAM)))
    registry = CallbackRegistry()
    register_rep3_bit_callbacks(registry)
    register_rep3_phase_callbacks(registry)

    results = Machine(out, num_qubits=9, registry=registry).eval(shots=20)
    assert all(result == [1] for result in results)
