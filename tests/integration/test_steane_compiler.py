"""Structural and executable tests for the Steane [[7,1,3]] compiler."""

import logging

import pytest
from xdsl.dialects.func import CallOp, FuncOp, ReturnOp as FuncReturn

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, HOp, SOp, XOp, ZOp
from qstack.dialect.core import (
    DecodeOp,
    InvokeOp,
    KernelOp,
    MeasureOp,
    ReturnOp as KernelReturn,
    SelectOp,
)
from qstack.passes.cliffords2h2 import compile_cliffords_to_h2
from qstack.passes.steane import (
    SteaneCompileError,
    _FunctionRewriter,
    compile_steane,
    register_steane_callbacks,
    steane_decode_bits,
    steane_syndrome_label,
)
from qstack.runtime import CallbackRegistry, Machine
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.verifier import verify_module
from tests.integration.test_prepare_one_qasm import PREPARE_ONE

_ZERO = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
measure q[0] -> c[0];
"""

_ONE = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
x q[0];
measure q[0] -> c[0];
"""

_BELL = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[2];
creg c[2];
h q[0];
cx q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""


def _compile(source: str):
    return compile_steane(lower(parse(source)))


def _registry() -> CallbackRegistry:
    registry = CallbackRegistry()
    register_steane_callbacks(registry)
    return registry


def test_steane_widens_allocations_and_measurements() -> None:
    module = _compile(_ONE)
    main = next(
        op
        for op in module.body.ops
        if isinstance(op, FuncOp) and op.sym_name.data == "main"
    )
    outer_kernel = next(op for op in main.body.block.ops if isinstance(op, KernelOp))
    assert len(outer_kernel.body.block.args) == 7
    assert len(outer_kernel.results) == 7
    assert len([op for op in module.walk() if isinstance(op, DecodeOp)]) == 1
    assert len([op for op in module.walk() if isinstance(op, SelectOp)]) >= 2
    verify_module(module)


def test_steane_prepares_encoded_zero_and_transversal_x() -> None:
    zero = _compile(_ZERO)
    one = _compile(_ONE)
    assert len([op for op in one.walk() if isinstance(op, XOp)]) >= 7
    assert all(
        result == [0]
        for result in Machine(
            zero, num_qubits=10, registry=_registry(), seed=7
        ).eval(shots=5)
    )
    assert all(
        result == [1]
        for result in Machine(
            one, num_qubits=10, registry=_registry(), seed=7
        ).eval(shots=5)
    )


def test_steane_bell_state_preserves_logical_correlation() -> None:
    module = _compile(_BELL)
    results = Machine(
        module,
        num_qubits=17,
        registry=_registry(),
        seed=11,
    ).eval(shots=12)
    assert {tuple(result) for result in results} <= {(0, 0), (1, 1)}


def test_steane_decoder_corrects_every_single_bit_fault() -> None:
    assert steane_decode_bits(*([0] * 7)) == 0
    assert steane_decode_bits(*([1] * 7)) == 1
    for index in range(7):
        zero_fault = [0] * 7
        zero_fault[index] = 1
        one_fault = [1] * 7
        one_fault[index] = 0
        assert steane_decode_bits(*zero_fault) == 0
        assert steane_decode_bits(*one_fault) == 1


def test_steane_syndrome_selector_covers_every_fault() -> None:
    assert steane_syndrome_label(0, 0, 0) == "none"
    labels = {
        steane_syndrome_label(*syndrome)
        for syndrome in (
            (0, 0, 1),
            (0, 1, 0),
            (0, 1, 1),
            (1, 0, 0),
            (1, 0, 1),
            (1, 1, 0),
            (1, 1, 1),
        )
    }
    assert labels == {str(index) for index in range(7)}


def test_steane_callbacks_report_evaluation_details(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="qstack"):
        assert steane_syndrome_label(0, 1, 0) == "5"
        assert steane_decode_bits(*([0] * 7)) == 0

    assert "syndrome: (0, 1, 0), correction: 5" in caplog.text
    assert (
        "outcome: [0, 0, 0, 0, 0, 0, 0], "
        "syndrome: (0, 0, 0), correction: None"
    ) in caplog.text


def test_steane_machine_reports_runtime_evaluation(caplog) -> None:
    module = _compile(_ONE)
    with caplog.at_level(logging.DEBUG, logger="qstack"):
        result = Machine(
            module, num_qubits=10, registry=_registry(), seed=7
        ).eval(shots=1)

    assert result.data == [[1]]
    assert "restart: 10" in caplog.text
    assert "eval: h [" in caplog.text
    assert "outcome:" in caplog.text
    assert "select: steane_syndrome" in caplog.text
    assert "decode: steane_decode" in caplog.text


def test_steane_output_can_lower_to_h2_and_execute() -> None:
    module = _compile(_ONE)
    compile_cliffords_to_h2(module)
    verify_module(module)
    assert not any(
        isinstance(op, (HOp, XOp, ZOp, CxOp))
        for op in module.walk()
    )
    result = Machine(
        module,
        num_qubits=10,
        registry=_registry(),
        seed=3,
    ).eval(shots=1)
    assert result.data == [[1]]


def test_steane_rejects_unsupported_cliffords_explicitly() -> None:
    source = """
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

qreg q[1];
creg c[1];
s q[0];
measure q[0] -> c[0];
"""
    with pytest.raises(SteaneCompileError, match="cliffords.s"):
        _compile(source)


def test_steane_support_declarations_have_stable_signatures() -> None:
    module = _compile(_ZERO)
    symbols = {
        op.sym_name.data: op
        for op in module.body.ops
        if isinstance(op, FuncOp)
    }
    decoder = symbols["steane_decode"]
    selector = symbols["steane_syndrome"]
    assert decoder.is_declaration
    assert "qstack.decoder" in decoder.attributes
    assert [type(typ) for typ in decoder.function_type.inputs.data] == [BitType] * 7
    assert [type(typ) for typ in decoder.function_type.outputs.data] == [BitType]
    assert selector.is_declaration
    assert "qstack.selector" in selector.attributes
    correction = symbols["__steane_correct_x_0"]
    assert [type(typ) for typ in correction.function_type.inputs.data] == [
        QubitType
    ] * 7


def test_steane_preserves_recursive_selector_workflow() -> None:
    source = lower(parse(PREPARE_ONE))
    module = compile_steane(source)
    verify_module(module)
    symbols = {
        op.sym_name.data: op
        for op in module.body.ops
        if isinstance(op, FuncOp)
    }
    prepare_one = symbols["prepare_one"]
    selector = symbols["repeat_until_one"]
    assert [type(typ) for typ in prepare_one.function_type.inputs.data] == [
        QubitType
    ] * 7
    assert [type(typ) for typ in prepare_one.function_type.outputs.data] == [
        QubitType
    ] * 7
    assert selector.is_declaration
    assert "qstack.selector" in selector.attributes


def test_steane_rewriter_uses_complete_handler_registry() -> None:
    assert set(_FunctionRewriter({}).handlers) == {
        HOp,
        XOp,
        ZOp,
        CxOp,
        MeasureOp,
        KernelOp,
        DecodeOp,
        SelectOp,
        InvokeOp,
        CallOp,
        KernelReturn,
        FuncReturn,
    }
