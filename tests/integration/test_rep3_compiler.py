"""Tests for the 3-bit repetition compiler pass.

Scope mirrors the legacy ``src/qstack/compilers/rep3_trivial.py``:

  - Every ``!qstack.qubit`` value becomes three physical qubits.
  - Cliffords ``H`` / ``X`` / ``Z`` are applied transversally (3× each).
  - Each ``qstack.measure`` becomes three measures plus a
    ``qstack.decode @majority_vote`` consuming the three resulting bits.

The complete pass also widens function boundaries and preserves calls,
selectors, continuation menus, and indirect invocation.
"""

import pytest
from xdsl.dialects.builtin import FunctionType, ModuleOp, UnitAttr
from xdsl.dialects.func import CallOp, FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Block, Region

from qstack_mlir.dialect import BitType, QubitType
from qstack_mlir.dialect.cliffords import CxOp, CzOp, HOp, XOp
from qstack_mlir.dialect.core import (
    DecodeOp,
    InvokeOp,
    KernelOp,
    MeasureOp,
    ReturnOp as KernelReturn,
    SelectOp,
)
from qstack_mlir.passes.rep3_trivial import (
    Rep3CompileError,
    compile_rep3,
    register_rep3_callbacks,
)
from qstack_mlir.surface.lowering import lower
from qstack_mlir.surface.parser import parse
from qstack_mlir.verifier import verify_module
from tests.integration.test_prepare_one_qasm import PREPARE_ONE

FLIP_PROGRAM = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
x q[0];
measure q[0] -> c[0];
"""


def _module(src: str) -> ModuleOp:
    return lower(parse(src))


def _walk(module: ModuleOp, op_type):
    return [op for op in module.walk() if isinstance(op, op_type)]


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------


def test_rep3_expands_main_signature() -> None:
    src = _module(FLIP_PROGRAM)
    out = compile_rep3(src)
    main = next(op for op in out.body.ops if isinstance(op, FuncOp) and op.sym_name.data == "main")
    # main still returns a single (decoded) bit, but the kernel inside it
    # now allocates 3 physical qubits.
    assert [type(t) for t in main.function_type.outputs.data] == [BitType]
    kernel = next(op for op in main.body.block.ops if isinstance(op, KernelOp))
    assert len(kernel.body.block.args) == 3


def test_rep3_triplicates_gates() -> None:
    out = compile_rep3(_module(FLIP_PROGRAM))
    assert len(_walk(out, XOp)) == 3
    assert len(_walk(out, MeasureOp)) == 3


def test_rep3_inserts_decode() -> None:
    out = compile_rep3(_module(FLIP_PROGRAM))
    decodes = _walk(out, DecodeOp)
    assert len(decodes) == 1
    dec = decodes[0]
    assert dec.callee.root_reference.data == "majority_vote"
    assert len(list(dec.bit_operands)) == 3


def test_rep3_module_passes_verifier() -> None:
    out = compile_rep3(_module(FLIP_PROGRAM))
    verify_module(out)


# ---------------------------------------------------------------------------
# Semantic check: emulate the compiled program.
# ---------------------------------------------------------------------------


def test_rep3_runtime_runs_1000_shots_all_one() -> None:
    from qstack_mlir.runtime import CallbackRegistry, Machine

    out = compile_rep3(_module(FLIP_PROGRAM))
    reg = CallbackRegistry()
    register_rep3_callbacks(reg)

    machine = Machine(out, num_qubits=4, registry=reg)
    results = machine.eval(shots=1000)
    assert all(
        r == [1] for r in results
    ), f"expected every shot to return [1], saw {sorted({tuple(r) for r in results})}"


# ---------------------------------------------------------------------------
# Coverage of other transversal Cliffords.
# ---------------------------------------------------------------------------


HADAMARD_PROGRAM = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
h q[0];
measure q[0] -> c[0];
"""


def test_rep3_triplicates_h_gates() -> None:
    out = compile_rep3(_module(HADAMARD_PROGRAM))
    assert len(_walk(out, HOp)) == 3


CZ_PROGRAM = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[2];
creg c[2];
h q[0];
cz q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""


def test_rep3_triplicates_cz_gates() -> None:
    out = compile_rep3(_module(CZ_PROGRAM))
    assert len(_walk(out, CzOp)) == 3
    assert len(_walk(out, MeasureOp)) == 6
    verify_module(out)


def test_rep3_rewrites_nested_unitary_kernel() -> None:
    outer_body = Block(arg_types=[QubitType()])
    inner_body = Block(arg_types=[])
    h = HOp(outer_body.args[0])
    inner_body.add_op(h)
    inner_body.add_op(KernelReturn(operands=[h.result]))
    inner = KernelOp(
        result_types=[QubitType()],
        region=Region([inner_body]),
    )
    outer_body.add_op(inner)
    measure = MeasureOp(operand=inner.results[0])
    outer_body.add_op(measure)
    outer_body.add_op(KernelReturn(operands=[measure.result]))
    outer = KernelOp(result_types=[BitType()], region=Region([outer_body]))

    main_body = Block()
    main_body.add_op(outer)
    main_body.add_op(FuncReturn.create(operands=[outer.results[0]]))
    source = ModuleOp(
        [
            FuncOp(
                "main",
                FunctionType.from_lists([], [BitType()]),
                Region([main_body]),
            )
        ]
    )

    out = compile_rep3(source)
    assert len(_walk(out, KernelOp)) == 2
    assert len(_walk(out, HOp)) == 3
    verify_module(out)


# ---------------------------------------------------------------------------
# Recursive selector workflow and pass composition.
# ---------------------------------------------------------------------------


def _symbols(module: ModuleOp) -> dict[str, FuncOp]:
    return {
        op.sym_name.data: op
        for op in module.body.ops
        if isinstance(op, FuncOp)
    }


def test_rep3_rewrites_prepare_one_quantum_dataflow() -> None:
    source = _module(PREPARE_ONE)
    out = compile_rep3(source)
    verify_module(out)

    symbols = _symbols(out)
    prepare_one = symbols["prepare_one"]
    assert [type(t) for t in prepare_one.function_type.inputs.data] == [QubitType] * 3
    assert [type(t) for t in prepare_one.function_type.outputs.data] == [QubitType] * 3

    # prepare_one's logical H and CX are both transversal.
    assert len(_walk(prepare_one, HOp)) == 3
    assert len(_walk(prepare_one, CxOp)) == 3

    # Calls, selects, and invokes survive with widened quantum signatures.
    assert _walk(out, CallOp)
    select = _walk(prepare_one, SelectOp)[0]
    invoke = _walk(prepare_one, InvokeOp)[0]
    assert len(select.result.type.inputs.data) == 3
    assert len(select.result.type.outputs.data) == 3
    assert len(list(invoke.args)) == 3
    assert len(list(invoke.results)) == 3


def test_rep3_preserves_selector_and_continuation_symbols() -> None:
    source = _module(PREPARE_ONE)
    source_select = _walk(source, SelectOp)[0]
    out = compile_rep3(source)
    symbols = _symbols(out)
    output_select = _walk(out, SelectOp)[0]

    selector = symbols["repeat_until_one"]
    assert selector.is_declaration
    assert "qstack.selector" in selector.attributes
    assert selector.function_type == _symbols(source)["repeat_until_one"].function_type
    assert output_select.callee == source_select.callee
    assert output_select.continuations == source_select.continuations


def test_rep3_does_not_mutate_source_module() -> None:
    source = _module(FLIP_PROGRAM)
    out = compile_rep3(source)

    assert out is not source
    assert len(_walk(source, XOp)) == 1
    assert len(_walk(source, MeasureOp)) == 1
    verify_module(source)
    verify_module(out)


def test_rep3_adds_one_majority_vote_declaration() -> None:
    out = compile_rep3(_module(PREPARE_ONE))
    declarations = [
        op
        for op in out.body.ops
        if isinstance(op, FuncOp) and op.sym_name.data == "majority_vote"
    ]
    assert len(declarations) == 1
    declaration = declarations[0]
    assert declaration.is_declaration
    assert "qstack.decoder" in declaration.attributes
    assert [type(t) for t in declaration.function_type.inputs.data] == [BitType] * 3
    assert [type(t) for t in declaration.function_type.outputs.data] == [BitType]


def test_rep3_preserves_existing_decoder_declaration() -> None:
    source = _module(FLIP_PROGRAM)
    declaration = FuncOp.external(
        "custom_decoder",
        [BitType(), BitType()],
        [BitType()],
    )
    declaration.attributes["qstack.decoder"] = UnitAttr()
    source.body.block.add_op(declaration)

    out = compile_rep3(source)
    cloned = _symbols(out)["custom_decoder"]
    assert cloned.function_type == declaration.function_type
    assert cloned.is_declaration
    assert "qstack.decoder" in cloned.attributes


def test_rep3_rejects_incompatible_majority_vote_symbol() -> None:
    source = _module(FLIP_PROGRAM)
    source.body.block.add_op(
        FuncOp.external(
            "majority_vote",
            [BitType()],
            [BitType()],
        )
    )
    with pytest.raises(Rep3CompileError, match="already exists"):
        compile_rep3(source)


def test_rep3_composes_with_itself() -> None:
    once = compile_rep3(_module(PREPARE_ONE))
    twice = compile_rep3(once)
    verify_module(twice)

    symbols = _symbols(twice)
    prepare_one = symbols["prepare_one"]
    assert [type(t) for t in prepare_one.function_type.inputs.data] == [QubitType] * 9
    assert [type(t) for t in prepare_one.function_type.outputs.data] == [QubitType] * 9
    assert len([name for name in symbols if name == "majority_vote"]) == 1
    assert len(_walk(prepare_one, HOp)) == 9
    assert len(_walk(prepare_one, CxOp)) == 9


def _prepare_one_registry():
    from qstack_mlir.runtime import CallbackRegistry

    registry = CallbackRegistry()

    @registry.selector("repeat_until_one")
    def _pick(*, b0):
        return "0" if b0 == 1 else "1"

    register_rep3_callbacks(registry)
    return registry


def test_rep3_prepare_one_executes() -> None:
    from qstack_mlir.runtime import Machine

    out = compile_rep3(_module(PREPARE_ONE))
    results = Machine(
        out,
        num_qubits=6,
        registry=_prepare_one_registry(),
    ).eval(shots=50)
    assert all(result == [1] for result in results)


def test_rep3_twice_prepare_one_executes() -> None:
    from qstack_mlir.runtime import Machine

    out = compile_rep3(compile_rep3(_module(PREPARE_ONE)))
    results = Machine(
        out,
        num_qubits=18,
        registry=_prepare_one_registry(),
    ).eval(shots=5)
    assert all(result == [1] for result in results)
