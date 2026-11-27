"""Exact source-callee substitution, including allocations and host effects."""

from dataclasses import replace

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Block, Region

from qstack.compilation import CompilationResult
from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, HOp
from qstack.dialect.core import AllocOp, CallOp, DecodeOp, DecoderOp, KernelOp, MeasureOp, ReturnOp
from qstack.passes.inline import InlineCalls
from qstack.verification import verify


def _main_block():
    """An entry block for @main, which borrows nothing, and one allocated qubit."""
    block = Block()
    allocation = AllocOp()
    block.add_op(allocation)
    return block, allocation.result


def _program():
    worker = Block(arg_types=[QubitType()])
    fresh = AllocOp()
    cx = CxOp(fresh.result, worker.args[0])
    measure = MeasureOp(operand=cx.results[0])
    decode = DecodeOp(callee="log", bit_operands=[measure.result])
    worker.add_ops([fresh, cx, measure, decode, ReturnOp(operands=[cx.results[1], decode.result])])
    helper = KernelOp("worker", input_types=[QubitType()], result_types=[QubitType(), BitType()], region=Region([worker]))
    main, qubit = _main_block()
    call = CallOp("worker", [qubit], [QubitType(), BitType()])
    last = MeasureOp(operand=call.results[0])
    main.add_ops([call, last, ReturnOp(operands=[last.result, call.results[1]])])
    return ModuleOp([DecoderOp("log", 1), helper, KernelOp("main", input_types=[], result_types=[BitType(), BitType()], region=Region([main]))])


def test_inline_copies_callback_body_and_fresh_allocations(tmp_path):
    source = _program()
    result = InlineCalls().run(source).save(tmp_path / "inline.json")
    main = next(op for op in result.module.body.ops if isinstance(op, KernelOp) and op.sym_name.data == "main")
    assert sum(isinstance(op, AllocOp) for op in main.body.block.ops) == 2
    assert not any(isinstance(op, CallOp) for op in main.body.block.ops)
    assert any(isinstance(op, DecodeOp) for op in main.body.block.ops)
    inline = next(rule for rule in result.witness.rules if rule.kind == "inline")
    assert inline.callee == "worker"
    assert any(op.name == "qstack.alloc" for op in inline.target.operations)
    assert verify(CompilationResult.load(result.artifact_path), backends=()).status == "VERIFIED"


def test_inline_source_is_the_original_callee_even_when_callee_is_also_inlined():
    leaf = Block(arg_types=[QubitType()])
    h = HOp(leaf.args[0])
    leaf.add_ops([h, ReturnOp(operands=[h.result])])
    worker = Block(arg_types=[QubitType()])
    nested = CallOp("leaf", [worker.args[0]], [QubitType()])
    worker.add_ops([nested, ReturnOp(operands=nested.results)])
    main, qubit = _main_block()
    call = CallOp("worker", [qubit], [QubitType()])
    m = MeasureOp(operand=call.results[0])
    main.add_ops([call, m, ReturnOp(operands=[m.result])])
    source = ModuleOp([
        KernelOp("leaf", input_types=[QubitType()], result_types=[QubitType()], region=Region([leaf])),
        KernelOp("worker", input_types=[QubitType()], result_types=[QubitType()], region=Region([worker])),
        KernelOp("main", input_types=[], result_types=[BitType()], region=Region([main])),
    ])
    result = InlineCalls().run(CompilationResult.from_module(source))
    assert verify(result, backends=()).status == "VERIFIED"
    rule = next(rule for rule in result.witness.rules if rule.kind == "inline" and rule.callee == "worker")
    assert [op.name for op in rule.target.operations] == ["qstack.call"]


def test_inline_handles_empty_forwarding_callee():
    worker = Block(arg_types=[QubitType()])
    worker.add_op(ReturnOp(operands=[worker.args[0]]))
    main, qubit = _main_block()
    call = CallOp("id", [qubit], [QubitType()])
    m = MeasureOp(operand=call.results[0])
    main.add_ops([call, m, ReturnOp(operands=[m.result])])
    source = ModuleOp([
        KernelOp("id", input_types=[QubitType()], result_types=[QubitType()], region=Region([worker])),
        KernelOp("main", input_types=[], result_types=[BitType()], region=Region([main])),
    ])
    result = InlineCalls().run(CompilationResult.from_module(source))
    assert verify(result, backends=()).status == "VERIFIED"
    assert not next(rule for rule in result.witness.rules if rule.kind == "inline").target.operations


def test_recursive_inlining_is_one_layer():
    worker = Block(arg_types=[QubitType()])
    h = HOp(worker.args[0])
    recursive = CallOp("worker", [h.result], [QubitType()])
    worker.add_ops([h, recursive, ReturnOp(operands=recursive.results)])
    main, qubit = _main_block()
    call = CallOp("worker", [qubit], [QubitType()])
    measure = MeasureOp(operand=call.results[0])
    main.add_ops([call, measure, ReturnOp(operands=[measure.result])])
    source = ModuleOp([
        KernelOp("worker", input_types=[QubitType()], result_types=[QubitType()], region=Region([worker])),
        KernelOp("main", input_types=[], result_types=[BitType()], region=Region([main])),
    ])
    result = InlineCalls().run(CompilationResult.from_module(source))
    assert verify(result, backends=()).status == "VERIFIED"
    assert sum(isinstance(op, CallOp) for op in result.module.walk()) == 2


def test_inline_rejects_forged_callee_rule(tmp_path):
    source = CompilationResult.from_module(_program())
    result = InlineCalls().run(source)
    rules = tuple(replace(rule, callee="main") if rule.kind == "inline" else rule for rule in result.witness.rules)
    witness = replace(result.witness, rules=rules)
    forged = CompilationResult.from_step(source, result.module, witness, artifact_path=tmp_path / "forged.json")
    report = verify(forged, backends=())
    assert report.status == "REFUTED"
    assert any("inline source" in rule.detail for rule in report.rules)
