"""Tests for Mermaid dataflow visualization."""

import pytest
from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr
from xdsl.ir import Block, Region

from qstack.dialect.cliffords import CxOp, HOp
from qstack.dialect.toy import SkewOp
from qstack.dialect.core import (
    BitType,
    CallOp,
    KernelOp,
    MeasureOp,
    QubitType,
    ReturnOp,
    SelectOp,
    SelectorOp,
)
from qstack.visualize import dataflow


def _bell_module() -> ModuleOp:
    block = Block(arg_types=[QubitType(), QubitType()])
    h = HOp(block.args[0]); block.add_op(h)
    cx = CxOp(h.result, block.args[1]); block.add_op(cx)
    left = MeasureOp(operand=cx.control_out); block.add_op(left)
    right = MeasureOp(operand=cx.target_out); block.add_op(right)
    block.add_op(ReturnOp(operands=[left.result, right.result]))
    main = KernelOp("main", input_types=[], result_types=[BitType(), BitType()], allocates=2, region=Region([block]))
    return ModuleOp([main])


def test_dataflow_emits_ssa_wires_as_mermaid_edges() -> None:
    mermaid = dataflow(_bell_module()).to_mermaid()
    assert 'arg0(["%0 (fresh)"])' in mermaid
    assert 'op0["h"]' in mermaid
    assert 'arg0 -- "%0" --> op0' in mermaid
    assert 'op1 -- "%3" --> op2' in mermaid
    assert 'op2 == "%5" ==> return' in mermaid
    assert 'op2{{"measure"}}' in mermaid
    assert 'hostIn(("host"))' in mermaid
    assert 'hostIn -. "host" .-> return' in mermaid


def test_dataflow_rejects_unknown_kernel() -> None:
    with pytest.raises(ValueError, match="@missing"):
        dataflow(_bell_module(), kernel="missing")


def test_dataflow_includes_operation_properties_in_node_labels() -> None:
    block = Block(arg_types=[QubitType()])
    skew = SkewOp(block.args[0], 0.8); block.add_op(skew)
    measured = MeasureOp(operand=skew.result); block.add_op(measured)
    block.add_op(ReturnOp(operands=[measured.result]))
    module = ModuleOp([
        KernelOp("main", input_types=[], result_types=[BitType()], allocates=1, region=Region([block]))
    ])
    assert 'skew<br/>bias = 0.8' in dataflow(module).to_mermaid()


def test_dataflow_threads_host_through_select_and_callback_call() -> None:
    case_block = Block(arg_types=[QubitType()])
    case_block.add_op(ReturnOp(operands=[case_block.args[0]]))
    case = KernelOp(
        "case", input_types=[QubitType()], result_types=[QubitType()], allocates=0,
        region=Region([case_block]),
    )

    worker_block = Block(arg_types=[QubitType(), QubitType()])
    measured = MeasureOp(operand=worker_block.args[1]); worker_block.add_op(measured)
    select = SelectOp(
        callee="choose", bit_operands=[measured.result],
        cases={"done": SymbolRefAttr("case")}, case_arguments=[worker_block.args[0]],
        result_types=[QubitType()],
    )
    worker_block.add_op(select); worker_block.add_op(ReturnOp(operands=[select.results[0]]))
    worker = KernelOp(
        "worker", input_types=[QubitType()], result_types=[QubitType()], allocates=1,
        region=Region([worker_block]),
    )

    main_block = Block(arg_types=[QubitType()])
    call = CallOp("worker", [main_block.args[0]], [QubitType()]); main_block.add_op(call)
    main_block.add_op(ReturnOp(operands=[call.results[0]]))
    main = KernelOp(
        "main", input_types=[], result_types=[QubitType()], allocates=1,
        region=Region([main_block]),
    )

    module = ModuleOp([SelectorOp("choose", 1), case, worker, main])
    main_mermaid = dataflow(module, inline_calls=False).to_mermaid()
    assert 'op0[["call @worker"]]' in main_mermaid
    assert 'subgraph call_kernel_main_op0["call @worker"]' in main_mermaid
    assert 'subgraph kernel_worker["@worker"]' in main_mermaid
    assert 'subgraph kernel_case["@case"]' not in main_mermaid
    flattened = dataflow(module).to_mermaid()
    assert 'call @worker' not in flattened
    assert 'subgraph inline_root_worker_1["@worker"]' in flattened
    assert "direction TB" in flattened
    assert 'select @choose' in flattened
    worker_mermaid = dataflow(module, kernel="worker").to_mermaid()
    assert 'op1[["select @choose<br/>{done: @case}"]]' in worker_mermaid
    assert 'hostIn -. "host" .-> op1' in worker_mermaid
    assert 'op1 -. "host" .-> return' in worker_mermaid
