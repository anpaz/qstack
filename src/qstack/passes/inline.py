"""One layer of exact call inlining, witnessed against the source callees."""

from __future__ import annotations

from xdsl.dialects.builtin import ArrayAttr, ModuleOp, StringAttr
from xdsl.ir import Block, Region

from qstack.compilation import CompilationResult
from qstack.dialect.core import CallOp, KernelOp
from qstack.encoding import Encoding
from qstack.passes.contracts import Replacement
from qstack.validation import PASS_HISTORY_ATTR, validate_module
from qstack.verification.builder import witness_from_replacements


class InlineCalls:
    """Copy each selected source callee once, including callbacks and allocations.

    Copies always come from the input module. Recursion is safe: newly copied
    calls are not visited again in this invocation. Subsequent optimization or
    encoding passes can transform the exposed body with their own witnesses.
    """

    pass_id = "qstack.inline"

    def __init__(self, callees: set[str] | None = None):
        self.callees = None if callees is None else frozenset(callees)

    def run(self, result: ModuleOp | CompilationResult) -> CompilationResult:
        if isinstance(result, ModuleOp):
            result = CompilationResult.from_module(result)
        source = result.module
        validate_module(source)
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
            block = Block(arg_types=kernel.input_types)
            values = dict(zip(kernel.body.block.args, block.args, strict=True))
            records = []
            for op in kernel.body.block.ops:
                inputs = tuple((value, values[value]) for value in op.operands)
                if op in calls:
                    callee = calls[op]
                    # The callee's allocations are operations, so they are copied
                    # with the rest of its body.
                    local = dict(zip(callee.body.block.args, (values[value] for value in op.operands), strict=True))
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
            target = KernelOp(kernel.sym_name.data, input_types=kernel.input_types, result_types=kernel.declared_result_types, region=Region([block]))
            target.attributes.update(kernel.attributes)
            target.location = kernel.location
            target_ops.append(target)
            replacements[kernel.sym_name.data] = records
        attributes = dict(source.attributes)
        history = attributes.get(PASS_HISTORY_ATTR, ArrayAttr([]))
        attributes[PASS_HISTORY_ATTR] = ArrayAttr([*history, StringAttr(self.pass_id)])
        target = ModuleOp(target_ops, attributes=attributes, sym_name=source.properties.get("sym_name"))
        target.location = source.location
        validate_module(target)
        witness = witness_from_replacements(source, target, replacements, encoding=Encoding.identity())
        return CompilationResult.from_step(result, target, witness)
