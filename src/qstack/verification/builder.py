"""Build an identity-encoding witness from checked pass replacements."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Mapping, Sequence

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import BlockArgument, OpResult, Operation, SSAValue

from qstack.dialect.core import KernelOp, UnitaryGateOp
from qstack.passes.base import Encoding, QubitGroup, Replacement
from qstack.verification.witness_check import _KernelSide, _circuit_at
from qstack.verification.model import Edge, KernelBoundary, Node, Rule, ValueRef, Witness


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

    all_nodes: list[Node] = []
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
        if len(old_args) != len(new_args) or old_kernel.allocation_count != new_kernel.allocation_count:
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
            if not source_ops:
                if target_ops or inputs != outputs or len(outputs) != 1:
                    raise NotImplementedError("only bare identity allocations are implemented")
                all_nodes.append(Node(node_id, kernel_name, "allocation", (), (), (), outputs))
                continue
            old_op = replacement.source_operations[0]
            new_op = replacement.target_operations[0] if target_ops else None
            copied = (
                len(source_ops) == len(target_ops) == 1
                and new_op is not None
                and old_op.name == new_op.name
                and old_op.attributes == new_op.attributes
                and old_op.properties == new_op.properties
            )
            if copied:
                all_nodes.append(Node(node_id, kernel_name, "identity", source_ops, target_ops, inputs, outputs))
                continue
            if not all(isinstance(op, UnitaryGateOp) for op in (*replacement.source_operations, *replacement.target_operations)):
                raise NotImplementedError(f"{node_id}: nonunitary rewrite needs another claim kind")
            provisional = Node(node_id, kernel_name, "rule", source_ops, target_ops, inputs, outputs)
            source_circuit = _circuit_at(provisional, old_side, local_edges, "source")
            target_circuit = _circuit_at(provisional, new_side, local_edges, "target")
            payload = json.dumps(
                {"source": asdict(source_circuit), "target": asdict(target_circuit)},
                sort_keys=True, separators=(",", ":"),
            )
            rule_id = "rule-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
            all_rules.setdefault(rule_id, Rule(rule_id, source_circuit, target_circuit))
            all_nodes.append(Node(node_id, kernel_name, "rule", source_ops, target_ops, inputs, outputs, rule_id))
        all_edges.extend(local_edges.values())

    return Witness.bind(
        source, target,
        rules=tuple(all_rules.values()), nodes=tuple(all_nodes),
        edges=tuple(all_edges), kernels=tuple(all_boundaries),
    )
