"""Build a single-step witness from checked pass replacements."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Mapping, Sequence

from xdsl.dialects.builtin import DenseArrayBase, ModuleOp, i32
from xdsl.ir import BlockArgument, Operation, OpResult, SSAValue
from xdsl.irdl import AttrSizedOperandSegments

from qstack.dialect.core import AllocOp, CallOp, KernelOp, MeasureOp, ReturnOp, SelectOp, UnitaryGateOp
from qstack.encoding import Encoding
from qstack.verification.witness_check import _KernelSide, _pattern_at, _callback_sources
from qstack.verification.model import Claim, Edge, KernelBoundary, Rule, ValueRef, Witness
from qstack.verification.patterns import has_qubits


if TYPE_CHECKING:
    from qstack.passes.contracts import Replacement


def _kernels(module: ModuleOp) -> dict[str, KernelOp]:
    return {
        op.sym_name.data: op for op in module.body.ops if isinstance(op, KernelOp)
    }


def _ref(value: SSAValue, side: _KernelSide) -> ValueRef:
    block = side.kernel.body.block
    if isinstance(value, BlockArgument):
        if value.owner is not block:
            raise ValueError("replacement references an argument from another kernel")
        return ValueRef("arg", value.index)
    if isinstance(value, OpResult):
        try:
            index = side.op_index[value.owner]
        except KeyError as exc:
            raise ValueError("replacement references a result from another kernel") from exc
        return ValueRef("result", index, value.index)
    raise TypeError("replacement references an unsupported SSA value")


def _widening_properties_match(source: Operation, target: Operation, encoding: Encoding) -> bool:
    if not isinstance(source, SelectOp):
        return source.properties == target.properties

    expected = dict(source.properties)
    # The selector bits stay scalar, while its case arguments follow the encoding.
    case_types = encoding.map_types(tuple(value.type for value in source.case_arguments))
    expected[AttrSizedOperandSegments.attribute_name] = DenseArrayBase.from_list(
        i32, [len(source.bit_operands), len(case_types)]
    )
    return expected == target.properties


def witness_from_replacements(
    source: ModuleOp,
    target: ModuleOp,
    replacements: Mapping[str, Sequence[Replacement]],
    *,
    encoding: Encoding,
) -> Witness:
    """Normalize checked replacement records into reusable rules and a claim graph."""
    source_kernels, target_kernels = _kernels(source), _kernels(target)
    if source_kernels.keys() < target_kernels.keys():
        raise NotImplementedError("witnesses for introduced kernels are unsupported")
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
        edges_by_pair: dict[tuple[ValueRef, tuple[ValueRef, ...]], str] = {}
        local_edges: dict[str, Edge] = {}

        def edge(source_value: SSAValue, bundle: tuple[SSAValue, ...]) -> str:
            key = (_ref(source_value, old_side), tuple(_ref(value, new_side) for value in bundle))
            if key not in edges_by_pair:
                edge_id = f"{kernel_name}:e{len(edges_by_pair)}"
                edges_by_pair[key] = edge_id
                local_edges[edge_id] = Edge(edge_id, kernel_name, (key[0],), key[1])
            return edges_by_pair[key]

        old_args = tuple(old_kernel.body.block.args)
        target_args = tuple(new_kernel.body.block.args)
        if tuple(arg.type for arg in target_args) != encoding.map_types(tuple(arg.type for arg in old_args)):
            raise ValueError(f"@{kernel_name}: target arguments disagree with the encoding")
        borrowed = []
        offset = 0
        for old in old_args:
            width = len(encoding.map_types((old.type,)))
            borrowed.append(edge(old, target_args[offset:offset + width]))
            offset += width
        all_boundaries.append(KernelBoundary(kernel_name, tuple(borrowed)))

        for ordinal, replacement in enumerate(replacements[kernel_name]):
            node_id = f"{kernel_name}:n{ordinal}"
            source_ops = tuple(old_side.op_index[op] for op in replacement.source_operations)
            target_ops = tuple(new_side.op_index[op] for op in replacement.target_operations)
            inputs = tuple(edge(old, (new,) if isinstance(new, SSAValue) else new.qubits) for old, new in replacement.inputs)
            outputs = tuple(edge(old, (new,) if isinstance(new, SSAValue) else new.qubits) for old, new in replacement.outputs)
            provisional = Claim(node_id, kernel_name, "", source_ops, target_ops, inputs, outputs)
            old_pattern = _pattern_at(provisional, old_side, local_edges, "source", source_hosts)
            new_pattern = _pattern_at(provisional, new_side, local_edges, "target", target_hosts)
            source_op = replacement.source_operations[0] if len(source_ops) == 1 else None
            callee = None
            if (
                old_pattern == new_pattern
                and len(old_pattern.operations) == 1
                and (encoding.is_identity or not has_qubits(old_pattern))
            ):
                kind = "identity"
            elif encoding.is_identity and isinstance(source_op, CallOp):
                kind = "inline"
                callee = source_op.callee.root_reference.data
            elif all(isinstance(op, UnitaryGateOp) for op in (
                *replacement.source_operations, *replacement.target_operations,
            )):
                kind = "gate"
            elif not encoding.is_identity and isinstance(source_op, AllocOp):
                kind = "allocation"
            elif not encoding.is_identity and isinstance(source_op, MeasureOp):
                kind = "measurement"
            elif (
                not encoding.is_identity
                and isinstance(source_op, (CallOp, ReturnOp, SelectOp))
                and len(target_ops) == 1
                and source_op.name == replacement.target_operations[0].name
                and _widening_properties_match(source_op, replacement.target_operations[0], encoding)
            ):
                kind = "widening"
            else:
                raise NotImplementedError(f"{node_id}: nonunitary rewrite needs another rule kind")
            definition = {"kind": kind, "callee": callee, "source": asdict(old_pattern), "target": asdict(new_pattern)}
            if not encoding.is_identity:
                definition["encoding"] = asdict(encoding)
            payload = json.dumps(
                definition,
                sort_keys=True, separators=(",", ":"), allow_nan=False,
            )
            rule_id = "rule-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
            all_rules.setdefault(rule_id, Rule(rule_id, old_pattern, new_pattern, kind, callee))
            all_claims.append(Claim(node_id, kernel_name, rule_id, source_ops, target_ops, inputs, outputs))
        all_edges.extend(local_edges.values())

    return Witness.bind(
        source, target,
        encoding=encoding,
        rules=tuple(all_rules.values()), claims=tuple(all_claims),
        edges=tuple(all_edges), kernels=tuple(all_boundaries),
    )
