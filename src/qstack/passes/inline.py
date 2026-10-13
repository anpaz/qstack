"""One layer of exact call inlining, witnessed against the source callees."""

from __future__ import annotations

from xdsl.dialects.builtin import ArrayAttr, ModuleOp, StringAttr
from xdsl.ir import Block, Region

from qstack.compilation import CompilationResult
from qstack.dialect.core import CallOp, KernelOp, QubitType
from qstack.passes.base import Encoding, Replacement
from qstack.verifier import PASS_HISTORY_ATTR, verify_module


class InlineCalls:
    """Copy each selected source callee once, including callbacks and allocations.

    Copies always come from the input module. Recursion is safe: newly copied
    calls are not visited again in this invocation. Subsequent optimization or
    encoding passes can transform the exposed body with their own witnesses.
    """

    pass_id = "qstack.inline"

    def __init__(self, callees: set[str] | None = None):
        self.callees = None if callees is None else frozenset(callees)

    def run(self, result: CompilationResult) -> CompilationResult:
        from qstack.verification.builder import witness_from_replacements

        source = result.module
        source.verify()
        verify_module(source)
        kernels = {op.sym_name.data: op for op in source.body.ops if isinstance(op, KernelOp)}
        replacements = {}
        target_ops = []
        for kernel in source.body.ops:
            if not isinstance(kernel, KernelOp):
                target_ops.append(kernel.clone())
                continue
            calls = {
                op: kernels[op.callee.root_reference.data]
                for op in kernel.body.block.ops
                if isinstance(op, CallOp) and (self.callees is None or op.callee.root_reference.data in self.callees)
            }
            allocation_count = kernel.allocation_count + sum(callee.allocation_count for callee in calls.values())
            block = Block(arg_types=[*[QubitType() for _ in range(allocation_count)], *kernel.input_types])
            old_args = kernel.body.block.args
            values = dict(zip(old_args[:kernel.allocation_count], block.args[:kernel.allocation_count], strict=True))
            values.update(zip(old_args[kernel.allocation_count:], block.args[allocation_count:], strict=True))
            records = [Replacement((), (), ((arg, values[arg]),), ((arg, values[arg]),)) for arg in old_args[:kernel.allocation_count]]
            next_allocation = kernel.allocation_count
            for op in kernel.body.block.ops:
                inputs = tuple((value, values[value]) for value in op.operands)
                if op in calls:
                    callee = calls[op]
                    borrowed = callee.body.block.args[callee.allocation_count:]
                    local = dict(zip(borrowed, (values[value] for value in op.operands), strict=True))
                    fresh = block.args[next_allocation:next_allocation + callee.allocation_count]
                    local.update(zip(callee.body.block.args[:callee.allocation_count], fresh, strict=True))
                    next_allocation += callee.allocation_count
                    body = tuple(callee.body.block.ops)
                    emitted = []
                    for instruction in body[:-1]:
                        copied = instruction.clone(value_mapper=local)
                        emitted.append(copied)
                        local.update(zip(instruction.results, copied.results, strict=True))
                    outputs = tuple(local[value] for value in body[-1].operands)
                else:
                    copied = op.clone(value_mapper=values)
                    emitted = [copied]
                    outputs = tuple(copied.results)
                pairs = tuple(zip(op.results, outputs, strict=True))
                records.append(Replacement((op,), tuple(emitted), inputs, pairs))
                block.add_ops(emitted)
                values.update(pairs)
            target = KernelOp(kernel.sym_name.data, input_types=kernel.input_types, result_types=kernel.declared_result_types, allocates=allocation_count, region=Region([block]))
            target.attributes.update(kernel.attributes)
            target.location = kernel.location
            target_ops.append(target)
            replacements[kernel.sym_name.data] = records
        attributes = dict(source.attributes)
        history = attributes.get(PASS_HISTORY_ATTR, ArrayAttr([]))
        attributes[PASS_HISTORY_ATTR] = ArrayAttr([*history, StringAttr(self.pass_id)])
        target = ModuleOp(target_ops, attributes=attributes, sym_name=source.properties.get("sym_name"))
        target.location = source.location
        target.verify()
        verify_module(target)
        witness = witness_from_replacements(source, target, replacements, encoding=Encoding.identity())
        return CompilationResult.from_step(result, target, witness)
