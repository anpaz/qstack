from dataclasses import replace
import subprocess
import sys

import pytest
from xdsl.dialects.builtin import ArrayAttr, ModuleOp, StringAttr
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.core import AllocOp, CallOp, DecoderOp, KernelOp, MeasureOp, ReturnOp
from qstack.dialect.toy import MixOp, SkewOp
from qstack.passes import (
    LoweringContext,
    LoweringPass,
    PASS_HISTORY_ATTR,
    PassError,
    QubitGroup,
    Replacement,
    Encoding,
)
from qstack.passes.rep3_bit import Rep3BitLowering
from qstack.passes.rep3_phase import Rep3PhaseLowering
from qstack.passes.toy2cliffords import (
    ToyToCliffordsLowering,
    ToyToCliffordsLoweringError,
)
from qstack.surface.lowering import lower
from qstack.surface.parser import parse
from qstack.validation import LinearityError, validate_module


@pytest.mark.parametrize("first", ["qstack.passes.base", "qstack.verification"])
def test_passes_and_verification_import_in_either_order(first) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {first}; import qstack.passes.base; import qstack.verification"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def _toy(program: str):
    return lower(
        parse(
            f'''QSTACKQASM 0.1;
include "qstack/toy.inc";
qubit[1] q; bit[1] c; {program} measure q[0] -> c[0];'''
        )
    )


def _linear_values(module):
    for op in module.body.ops:
        if not isinstance(op, KernelOp):
            continue
        yield from op.body.block.args
        for inner in op.body.block.ops:
            yield from inner.results


def test_encoding_derives_target_types() -> None:
    assert Rep3BitLowering.encoding.map_types(
        (BitType(), QubitType(), BitType())
    ) == (
        BitType(),
        QubitType(),
        QubitType(),
        QubitType(),
        BitType(),
    )


def test_identity_encoding_preserves_signature() -> None:
    signature = (BitType(), QubitType(), BitType())

    assert Encoding.identity().map_types(signature) is signature


def test_only_nonidentity_qubits_group_flat_values() -> None:
    source = Block(arg_types=[BitType(), QubitType()])
    context = LoweringContext((), {})

    identity = ToyToCliffordsLowering()
    identity_target = Block(
        arg_types=identity.encoding.map_types(
            tuple(value.type for value in source.args)
        )
    )
    identity_values = identity._group_values(
        source.args, identity_target.args, context
    )
    assert identity_values == tuple(identity_target.args)

    encoded = Rep3BitLowering()
    encoded_target = Block(
        arg_types=encoded.encoding.map_types(
            tuple(value.type for value in source.args)
        )
    )
    encoded_values = encoded._group_values(source.args, encoded_target.args, context)
    assert encoded_values[0] is encoded_target.args[0]
    group = encoded_values[1]
    assert isinstance(group, QubitGroup)
    assert group.qubits == tuple(encoded_target.args[1:])


def test_lowering_builds_independently_owned_ir() -> None:
    source = _toy("mix q[0];")
    source_values = set(_linear_values(source))
    uses_before = {value: tuple(value.uses) for value in source_values}

    target = ToyToCliffordsLowering().run(source)

    validate_module(source)
    validate_module(target)
    assert any(isinstance(op, MixOp) for op in source.walk())
    assert not any(isinstance(op, MixOp) for op in target.walk())
    assert all(tuple(value.uses) == uses_before[value] for value in source_values)
    assert not any(
        operand in source_values
        for operation in target.walk()
        for operand in operation.operands
    )
    assert not ({id(op) for op in source.walk()} & {id(op) for op in target.walk()})


def test_failed_lowering_does_not_modify_source_uses() -> None:
    source = _toy("skew(0.25) q[0];")
    values = tuple(_linear_values(source))
    uses_before = {value: tuple(value.uses) for value in values}

    try:
        ToyToCliffordsLowering().run(source)
    except ToyToCliffordsLoweringError:
        pass
    else:  # pragma: no cover - guards the test setup
        raise AssertionError("skew unexpectedly lowered")

    validate_module(source)
    assert PASS_HISTORY_ATTR not in source.attributes
    assert any(isinstance(op, SkewOp) for op in source.walk())
    assert all(tuple(value.uses) == uses_before[value] for value in values)


@pytest.mark.parametrize(
    "history",
    [StringAttr("not-an-array"), ArrayAttr([StringAttr("valid"), BitType()])],
)
def test_module_verifier_rejects_malformed_pass_history(history) -> None:
    source = _toy("mix q[0];")
    source.attributes[PASS_HISTORY_ATTR] = history

    with pytest.raises(LinearityError, match="must be an array of strings"):
        validate_module(source)


def test_lowering_preserves_kernel_and_callback_metadata() -> None:
    source = ToyToCliffordsLowering().run(_toy("mix q[0];"))
    main = next(op for op in source.body.ops if isinstance(op, KernelOp))
    main.attributes["marker"] = StringAttr("kernel")
    declaration = DecoderOp("existing.1:decode", 1)
    declaration.attributes["marker"] = StringAttr("callback")
    source.body.block.add_op(declaration)

    target = Rep3BitLowering().run(source)
    target_main = next(
        op for op in target.body.ops if isinstance(op, KernelOp) and op.sym_name.data == "main"
    )
    target_declaration = next(
        op
        for op in target.body.ops
        if isinstance(op, DecoderOp) and op.sym_name.data == "existing.1:decode"
    )
    assert target_main.attributes["marker"] == StringAttr("kernel")
    assert target_declaration.attributes["marker"] == StringAttr("callback")
    assert target_declaration.sym_name.data == "existing.1:decode"


def test_pass_instance_does_not_reuse_run_state() -> None:
    lowering = Rep3BitLowering()
    first = lowering.run(ToyToCliffordsLowering().run(_toy("flip q[0];")))
    second = lowering.run(ToyToCliffordsLowering().run(_toy("flip q[0];")))
    first_names = [op.sym_name.data for op in first.body.ops if isinstance(op, DecoderOp)]
    second_names = [op.sym_name.data for op in second.body.ops if isinstance(op, DecoderOp)]
    assert first_names == second_names == ["rep3_bit.2:decode"]
    expected_history = ArrayAttr(
        [StringAttr("qstack.toy-to-cliffords"), StringAttr("qstack.rep3-bit")]
    )
    assert first.attributes[PASS_HISTORY_ATTR] == expected_history
    assert second.attributes[PASS_HISTORY_ATTR] == expected_history


def test_lowering_precomputes_recursive_call_signatures() -> None:
    recursive_block = Block(arg_types=[QubitType()])
    recursive_call = CallOp("recursive", [recursive_block.args[0]], [QubitType()])
    recursive_block.add_op(recursive_call)
    recursive_block.add_op(ReturnOp(operands=[recursive_call.results[0]]))
    recursive = KernelOp(
        "recursive",
        input_types=[QubitType()],
        result_types=[QubitType()],
        region=Region([recursive_block]),
    )
    main_block = Block()
    allocation = AllocOp()
    call = CallOp("recursive", [allocation.result], [QubitType()])
    main_block.add_ops([allocation, call])
    measure = MeasureOp(operand=call.results[0])
    main_block.add_op(measure)
    main_block.add_op(ReturnOp(operands=[measure.result]))
    main = KernelOp(
        "main",
        input_types=[],
        result_types=[BitType()],
        region=Region([main_block]),
    )

    target = Rep3BitLowering().run(ModuleOp([recursive, main]))
    validate_module(target)
    calls = [op for op in target.walk() if isinstance(op, CallOp)]
    assert all(len(op.arguments) == len(op.results) == 3 for op in calls)


def test_lowering_preserves_mixed_signature_order_while_widening_qubits() -> None:
    worker_block = Block(arg_types=[BitType(), QubitType()])
    worker_block.add_op(
        ReturnOp(operands=[worker_block.args[1], worker_block.args[0]])
    )
    worker = KernelOp(
        "worker",
        input_types=[BitType(), QubitType()],
        result_types=[QubitType(), BitType()],
        region=Region([worker_block]),
    )
    main_block = Block()
    allocations = [AllocOp(), AllocOp()]
    main_block.add_ops(allocations)
    first_measure = MeasureOp(operand=allocations[0].result)
    main_block.add_op(first_measure)
    call = CallOp(
        "worker",
        [first_measure.result, allocations[1].result],
        [QubitType(), BitType()],
    )
    main_block.add_op(call)
    second_measure = MeasureOp(operand=call.results[0])
    main_block.add_op(second_measure)
    main_block.add_op(ReturnOp(operands=[call.results[1], second_measure.result]))
    main = KernelOp(
        "main",
        input_types=[],
        result_types=[BitType(), BitType()],
        region=Region([main_block]),
    )

    target = Rep3BitLowering().run(ModuleOp([worker, main]))
    validate_module(target)
    target_worker = next(
        op for op in target.body.ops if isinstance(op, KernelOp) and op.sym_name.data == "worker"
    )
    assert target_worker.input_types == (
        BitType(),
        QubitType(),
        QubitType(),
        QubitType(),
    )
    assert target_worker.declared_result_types == (
        QubitType(),
        QubitType(),
        QubitType(),
        BitType(),
    )


def test_body_records_encoded_qubits_and_scalar_bits_after_preparation() -> None:
    class RecordingPhaseLowering(Rep3PhaseLowering):
        def lower_body(self, operations, inputs, context):
            self.entry = inputs
            self.replacements = super().lower_body(operations, inputs, context)
            return self.replacements

    source = ToyToCliffordsLowering().run(_toy("flip q[0];"))
    main = next(op for op in source.body.ops if isinstance(op, KernelOp))
    source_ops = tuple(main.body.block.ops)
    lowering = RecordingPhaseLowering()
    target = lowering.run(source)
    target_main = next(op for op in target.body.ops if isinstance(op, KernelOp))
    allocation, gate, measure, returned = lowering.replacements

    assert tuple(r.source_operations for r in lowering.replacements) == tuple(
        (op,) for op in source_ops
    )
    # @main borrows nothing; its qubit comes from a qstack.alloc, which the
    # encoding turns into three allocations prepared as encoded zero.
    assert lowering.entry == ()
    assert allocation.inputs == ()
    ((fresh, prepared),) = allocation.outputs
    assert fresh is source_ops[0].results[0]
    assert isinstance(prepared, QubitGroup)
    target_ops = tuple(target_main.body.block.ops)
    assert all(isinstance(op, AllocOp) for op in target_ops[:3])
    preparation = target_ops[3:6]
    assert allocation.target_operations == target_ops[:6]
    assert prepared.qubits == tuple(op.results[0] for op in preparation)
    assert gate.inputs == allocation.outputs
    assert isinstance(gate.outputs[0][1], QubitGroup)
    assert measure.inputs == gate.outputs
    assert measure.outputs == ((source_ops[2].results[0], measure.target_operations[-1].results[0]),)
    assert returned.inputs == measure.outputs
    assert returned.outputs == ()
    assert all(op.parent is target_main.body.block for r in lowering.replacements for op in r.target_operations)


def test_body_override_can_return_one_replacement_for_the_entire_body() -> None:
    class WholeBodyPass(LoweringPass):
        pass_id = "test.whole-body"

        def lower_body(self, operations, inputs, context):
            individual = super().lower_body(operations, inputs, context)
            return [Replacement(
                source_operations=tuple(operations),
                target_operations=tuple(op for r in individual for op in r.target_operations),
                inputs=inputs,
                outputs=(),  # The return operation is inside this fragment.
            )]

    source = _toy("mix q[0];")
    target = WholeBodyPass().run(source)
    source_main = next(op for op in source.body.ops if isinstance(op, KernelOp))
    target_main = next(op for op in target.body.ops if isinstance(op, KernelOp))
    assert source_main.body.is_structurally_equivalent(target_main.body)
    assert not ({id(op) for op in source.walk()} & {id(op) for op in target.walk()})


@pytest.mark.parametrize("change", [
    lambda rs: rs[1:],
    lambda rs: [rs[0], *rs],
    lambda rs: list(reversed(rs)),
    lambda rs: [replace(rs[0], source_operations=(rs[0].source_operations[0].clone(),)), *rs[1:]],
])
def test_body_rejects_missing_duplicated_reordered_or_substituted_source(change) -> None:
    class BadCoverage(LoweringPass):
        pass_id = "test.bad-coverage"

        def lower_body(self, operations, inputs, context):
            return change(super().lower_body(operations, inputs, context))

    source = _toy("mix q[0];")
    with pytest.raises(PassError, match="cover the source body exactly once"):
        BadCoverage().run(source)


@pytest.mark.parametrize(("change", "message"), [
    (lambda r: replace(r, inputs=()), "inputs do not match"),
    (lambda r: replace(r, outputs=()), "outputs do not match"),
    (lambda r: replace(r, inputs=((r.inputs[0][0], r.outputs[0][1]),)), "preceding boundary"),
    (lambda r: replace(r, outputs=((r.outputs[0][0], r.source_operations[0].results[0]),)), "output is not defined"),
    (lambda r: replace(r, outputs=((r.outputs[0][0], QubitGroup((r.outputs[0][1],))),)), "must be a scalar"),
    (lambda r: replace(r, target_operations=(*r.target_operations, *r.target_operations)), "duplicate target operation"),
    (lambda r: replace(r, target_operations=r.source_operations), "already attached"),
])
def test_body_rejects_malformed_replacement_boundaries(change, message) -> None:
    class BadBoundary(LoweringPass):
        pass_id = "test.bad-boundary"

        def lower_body(self, operations, inputs, context):
            replacements = super().lower_body(operations, inputs, context)
            # Replacement 0 is the allocation; 1 is the gate.
            replacements[1] = change(replacements[1])
            return replacements

    with pytest.raises(PassError, match=message):
        BadBoundary().run(_toy("mix q[0];"))


def test_body_rejects_target_wiring_outside_reported_inputs() -> None:
    class BadWiring(LoweringPass):
        pass_id = "test.bad-wiring"

        def lower_body(self, operations, inputs, context):
            replacements = super().lower_body(operations, inputs, context)
            target = replacements[1].target_operations[0]
            unrelated = Block(arg_types=[QubitType()])
            target.operands = (unrelated.args[0],)
            return replacements

    with pytest.raises(PassError, match="outside its replacement boundary"):
        BadWiring().run(_toy("mix q[0];"))


def test_body_rejects_mutation_of_the_source_kernel() -> None:
    class MutatingPass(LoweringPass):
        pass_id = "test.mutating"

        def lower_body(self, operations, inputs, context):
            replacements = super().lower_body(operations, inputs, context)
            operations[0].attributes["changed"] = StringAttr("invalid")
            return replacements

    with pytest.raises(PassError, match="modified the source kernel"):
        MutatingPass().run(_toy("mix q[0];"))


@pytest.mark.parametrize("fault", ["count", "width", "type"])
def test_handler_outputs_must_match_the_encoding(fault) -> None:
    class InvalidOutputs(Rep3BitLowering):
        def _lower_one_qubit(self, source, operands, context):
            operations, outputs = super()._lower_one_qubit(source, operands, context)
            if fault == "count":
                return operations, ()
            if fault == "type":
                return operations, (Block(arg_types=[BitType()]).args[0],)
            group = outputs[0]
            return operations, (QubitGroup(group.qubits[:2]),)

    source = ToyToCliffordsLowering().run(_toy("mix q[0];"))
    with pytest.raises(PassError, match="outputs for|must be a qubit group|expected"):
        InvalidOutputs().run(source)
