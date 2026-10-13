"""Build an identity-encoding witness from checked pass replacements."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Mapping, Sequence

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import BlockArgument, OpResult, SSAValue

from qstack.dialect.core import CallOp, KernelOp, UnitaryGateOp
from qstack.passes.base import Encoding, QubitGroup, Replacement
from qstack.verification.witness_check import _KernelSide, _pattern_at, _callback_sources
from qstack.verification.model import Claim, Edge, KernelBoundary, Rule, ValueRef, Witness


def _kernels(module: ModuleOp) -> dict[str, KernelOp]:
    return {
        op.sym_name.data: op for op in module.body.ops if isinstance(op, KernelOp)
    }


def _ref(value: SSAValue, kernel: KernelOp) -> ValueRef:
    block = kernel.body.block
    if isinstance(value, BlockArgument):
        if value.owner is not block:
            raise ValueError("replacement references an argument from another kernel")
        return ValueRef("arg", value.index)
    if isinstance(value, OpResult):
        ops = tuple(block.ops)
        try:
            index = ops.index(value.owner)
        except ValueError as exc:
            raise ValueError("replacement references a result from another kernel") from exc
        return ValueRef("result", index, value.index)
    raise TypeError("replacement references an unsupported SSA value")


def _scalar(value: SSAValue | QubitGroup) -> SSAValue:
    if isinstance(value, QubitGroup):
        raise NotImplementedError("witness builder currently supports identity encoding only")
    return value


def witness_from_replacements(
    source: ModuleOp,
    target: ModuleOp,
    replacements: Mapping[str, Sequence[Replacement]],
    *,
    encoding: Encoding,
) -> Witness:
    """Normalize checked replacement records into reusable rules and a claim graph."""
    if not encoding.is_identity:
        raise NotImplementedError("witness builder currently supports identity encoding only")
    source_kernels, target_kernels = _kernels(source), _kernels(target)
    if set(source_kernels) != set(target_kernels) or set(replacements) != set(source_kernels):
        raise ValueError("replacement records must cover the same kernel symbols on both sides")

    all_claims: list[Claim] = []
    source_hosts, target_hosts = _callback_sources(source), _callback_sources(target)
    all_edges: list[Edge] = []
    all_boundaries: list[KernelBoundary] = []
    all_rules: dict[str, Rule] = {}
    for kernel_name in source_kernels:
        old_kernel, new_kernel = source_kernels[kernel_name], target_kernels[kernel_name]
        old_side, new_side = _KernelSide(old_kernel), _KernelSide(new_kernel)
        edges_by_pair: dict[tuple[ValueRef, ValueRef], str] = {}
        local_edges: dict[str, Edge] = {}

        def edge(source_value: SSAValue, target_value: SSAValue | QubitGroup) -> str:
            key = (_ref(source_value, old_kernel), _ref(_scalar(target_value), new_kernel))
            if key not in edges_by_pair:
                edge_id = f"{kernel_name}:e{len(edges_by_pair)}"
                edges_by_pair[key] = edge_id
                local_edges[edge_id] = Edge(edge_id, kernel_name, (key[0],), (key[1],))
            return edges_by_pair[key]

        old_args = tuple(old_kernel.body.block.args)
        new_args = tuple(new_kernel.body.block.args)
        if len(old_kernel.input_types) != len(new_kernel.input_types):
            raise NotImplementedError("widened kernel boundaries require an encoding witness")
        borrowed = tuple(
            edge(old, new)
            for old, new in zip(
                old_args[old_kernel.allocation_count:],
                new_args[new_kernel.allocation_count:],
                strict=True,
            )
        )
        all_boundaries.append(KernelBoundary(kernel_name, borrowed))

        for ordinal, replacement in enumerate(replacements[kernel_name]):
            node_id = f"{kernel_name}:n{ordinal}"
            source_ops = tuple(old_side.op_index[op] for op in replacement.source_operations)
            target_ops = tuple(new_side.op_index[op] for op in replacement.target_operations)
            inputs = tuple(edge(old, new) for old, new in replacement.inputs)
            outputs = tuple(edge(old, new) for old, new in replacement.outputs)
            source_allocations: tuple[int, ...] = ()
            target_allocations: tuple[int, ...] = ()
            if not source_ops:
                if target_ops or inputs != outputs or len(outputs) != 1:
                    raise NotImplementedError("encoded allocation needs an encoding witness")
                source_allocations = (local_edges[outputs[0]].source[0].index,)
                target_allocations = (local_edges[outputs[0]].target[0].index,)
                inputs = ()
            else:
                boundary_values = {_scalar(value) for _, value in replacement.inputs}
                target_allocations = tuple(sorted({
                    value.index
                    for value in (
                        *(value for op in replacement.target_operations for value in op.operands),
                        *(_scalar(value) for _, value in replacement.outputs),
                    )
                    if isinstance(value, BlockArgument)
                    and value.owner is new_kernel.body.block
                    and value.index < new_kernel.allocation_count
                    and value not in boundary_values
                }))
            provisional = Claim(
                node_id, kernel_name, "", source_ops, target_ops, inputs, outputs,
                source_allocations, target_allocations,
            )
            old_pattern = _pattern_at(provisional, old_side, local_edges, "source", source_hosts)
            new_pattern = _pattern_at(provisional, new_side, local_edges, "target", target_hosts)
            callee = None
            if old_pattern == new_pattern and len(old_pattern.operations) == 1:
                kind = "identity"
            elif len(source_ops) == 1 and isinstance(replacement.source_operations[0], CallOp):
                kind = "inline"
                callee = replacement.source_operations[0].callee.root_reference.data
            elif (
                all(isinstance(op, UnitaryGateOp) for op in (
                    *replacement.source_operations, *replacement.target_operations,
                ))
                and not source_allocations
                and not target_allocations
            ):
                kind = "gate"
            else:
                raise NotImplementedError(f"{node_id}: nonunitary rewrite needs another rule kind")
            payload = json.dumps(
                {"kind": kind, "callee": callee, "source": asdict(old_pattern), "target": asdict(new_pattern)},
                sort_keys=True, separators=(",", ":"), allow_nan=False,
            )
            rule_id = "rule-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
            all_rules.setdefault(rule_id, Rule(rule_id, old_pattern, new_pattern, kind, callee))
            all_claims.append(Claim(
                node_id, kernel_name, rule_id, source_ops, target_ops, inputs, outputs,
                source_allocations, target_allocations,
            ))
        all_edges.extend(local_edges.values())

    return Witness.bind(
        source, target,
        rules=tuple(all_rules.values()), claims=tuple(all_claims),
        edges=tuple(all_edges), kernels=tuple(all_boundaries),
    )
