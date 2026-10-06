"""Check witness claims against both IR projections and their dataflow."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Operation, SSAValue

from qstack.callbacks import resolve_callback
from qstack.dialect.core import (
    CallOp,
    DecodeOp,
    DecoderOp,
    KernelOp,
    SelectOp,
    SelectorOp,
    UnitaryGateOp,
)
from qstack.verification.model import Circuit, Edge, Gate, Node, ValueRef, Witness


class WitnessError(ValueError):
    """The witness does not describe the actual source and target graphs."""


class UnsupportedWitnessError(WitnessError):
    """The witness uses a relation the current structural checker cannot handle."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WitnessError(message)


def _unique(items: tuple, label: str) -> dict[str, object]:
    result = {item.id: item for item in items}
    _require(len(result) == len(items), f"duplicate {label} ID")
    return result


def _kernels(module: ModuleOp) -> dict[str, KernelOp]:
    return {
        op.sym_name.data: op
        for op in module.body.ops
        if isinstance(op, KernelOp)
    }


def _declarations(module: ModuleOp) -> dict[str, Operation]:
    return {
        op.sym_name.data: op
        for op in module.body.ops
        if isinstance(op, (DecoderOp, SelectorOp))
    }


@dataclass
class _KernelSide:
    kernel: KernelOp

    def __post_init__(self) -> None:
        self.args = tuple(self.kernel.body.blocks[0].args)
        self.ops = tuple(self.kernel.body.blocks[0].ops)
        self.op_index = {op: index for index, op in enumerate(self.ops)}

    def value(self, ref: ValueRef) -> SSAValue:
        if ref.kind == "arg":
            _require(ref.slot == 0 and 0 <= ref.index < len(self.args), "invalid argument value reference")
            return self.args[ref.index]
        _require(ref.kind == "result", f"unknown value reference kind {ref.kind!r}")
        _require(0 <= ref.index < len(self.ops), "invalid operation value reference")
        results = self.ops[ref.index].results
        _require(0 <= ref.slot < len(results), "invalid operation result slot")
        return results[ref.slot]

    def region_boundary(self, indices: tuple[int, ...]) -> tuple[set[SSAValue], set[SSAValue]]:
        _require(len(set(indices)) == len(indices) and tuple(sorted(indices)) == indices, "region operations must be unique and ordered")
        _require(all(0 <= index < len(self.ops) for index in indices), "region operation index out of range")
        region = {self.ops[index] for index in indices}
        # A fragment may contain disjoint operations, but no dataflow path may
        # leave the fragment and later enter it again.
        frontier = [
            use.operation
            for op in region
            for result in op.results
            for use in result.uses
            if use.operation not in region
        ]
        visited: set[Operation] = set()
        while frontier:
            op = frontier.pop()
            _require(op not in region, "claim region has a path that leaves and re-enters")
            if op in visited:
                continue
            visited.add(op)
            frontier.extend(
                use.operation
                for result in op.results
                for use in result.uses
            )
        external_inputs = {
            operand
            for op in region
            for operand in op.operands
            if not isinstance(operand.owner, Operation) or operand.owner not in region
        }
        external_outputs = {
            result
            for op in region
            for result in op.results
            if any(use.operation not in region for use in result.uses)
        }
        return external_inputs, external_outputs


def _value_refs(
    node: Node, edge_map: dict[str, Edge], side: _KernelSide, *,
    projection: str, output: bool,
) -> tuple[SSAValue, ...]:
    ids = node.outputs if output else node.inputs
    return tuple(
        side.value(getattr(edge_map[edge_id], projection)[0])
        for edge_id in ids
    )


def _check_region(
    node: Node, side: _KernelSide, edge_map: dict[str, Edge], projection: str
) -> None:
    indices = node.source_ops if projection == "source" else node.target_ops
    inputs = _value_refs(node, edge_map, side, projection=projection, output=False)
    outputs = _value_refs(node, edge_map, side, projection=projection, output=True)
    _require(len(set(inputs)) == len(inputs), f"{node.id}: duplicate input value")
    _require(len(set(outputs)) == len(outputs), f"{node.id}: duplicate output value")
    actual_inputs, actual_outputs = side.region_boundary(indices)
    declared_inputs, declared_outputs = set(inputs), set(outputs)
    _require(actual_inputs <= declared_inputs, f"{node.id}: uncovered {projection} input")
    _require(actual_outputs <= declared_outputs, f"{node.id}: uncovered {projection} output")
    forwarded = declared_inputs - actual_inputs
    _require(forwarded == declared_outputs - actual_outputs, f"{node.id}: invalid {projection} forwarding")
    _require(not (actual_inputs & declared_outputs), f"{node.id}: consumed {projection} input was forwarded")
    _require(not (actual_outputs & declared_inputs), f"{node.id}: internal {projection} output is also an input")


def _circuit_at(
    node: Node, side: _KernelSide, edge_map: dict[str, Edge], projection: str
) -> Circuit:
    indices = node.source_ops if projection == "source" else node.target_ops
    inputs = _value_refs(node, edge_map, side, projection=projection, output=False)
    outputs = _value_refs(node, edge_map, side, projection=projection, output=True)
    _require(len(inputs) == len(outputs), f"{node.id}: unitary rule changes width")
    live: dict[SSAValue, int] = {value: index for index, value in enumerate(inputs)}
    gates: list[Gate] = []
    for index in indices:
        op = side.ops[index]
        _require(isinstance(op, UnitaryGateOp), f"{node.id}: rule contains nonunitary {op.name}")
        _require(len(op.operands) == len(op.results), f"{node.id}: gate does not thread its wires")
        try:
            wires = tuple(live.pop(value) for value in op.operands)
        except KeyError as exc:
            raise WitnessError(f"{node.id}: rule operand has no incoming wire") from exc
        _require(len(set(wires)) == len(wires), f"{node.id}: duplicate gate wire")
        try:
            gates.append(Gate.from_op(op, wires))
        except (TypeError, ValueError) as exc:
            raise UnsupportedWitnessError(f"{node.id}: cannot serialize {op.name}: {exc}") from exc
        live.update(zip(op.results, wires, strict=True))
    _require(
        len(live) == len(outputs) and all(live.get(value) == i for i, value in enumerate(outputs)),
        f"{node.id}: {projection} rule output order differs from its boundary",
    )
    return Circuit(len(inputs), tuple(gates))


def _same_circuit(actual: Circuit, expected: Circuit) -> bool:
    if actual.width != expected.width or len(actual.gates) != len(expected.gates):
        return False
    for left, right in zip(actual.gates, expected.gates, strict=True):
        if (
            left.name != right.name
            or left.wires != right.wires
            or left.parameters != right.parameters
            or left.attributes != right.attributes
            or left.array().shape != right.array().shape
            or not np.allclose(left.array(), right.array(), rtol=0, atol=1e-12)
        ):
            return False
    return True


def _check_identity(
    node: Node, source: _KernelSide, target: _KernelSide, edges: dict[str, Edge]
) -> None:
    _require(len(node.source_ops) == len(node.target_ops) == 1, f"{node.id}: identity must pair one operation")
    old = source.ops[node.source_ops[0]]
    new = target.ops[node.target_ops[0]]
    _require(
        old.name == new.name
        and old.attributes == new.attributes
        and old.properties == new.properties
        and tuple(value.type for value in old.operands) == tuple(value.type for value in new.operands)
        and tuple(value.type for value in old.results) == tuple(value.type for value in new.results),
        f"{node.id}: identity operation changed",
    )
    _require(len(node.inputs) == len(old.operands), f"{node.id}: identity input ports differ")
    _require(len(node.outputs) == len(old.results), f"{node.id}: identity output ports differ")
    for projection, side, op in (("source", source, old), ("target", target, new)):
        _require(
            tuple(op.operands) == _value_refs(node, edges, side, projection=projection, output=False)
            and tuple(op.results) == _value_refs(node, edges, side, projection=projection, output=True),
            f"{node.id}: {projection} identity port order differs",
        )


def _callback_sources(module: ModuleOp) -> dict[str, set[str]]:
    kernels = _kernels(module)
    uses: dict[str, set[str]] = {name: set() for name in kernels}
    changed = True
    while changed:
        changed = False
        for name, kernel in kernels.items():
            discovered = set(uses[name])
            for op in kernel.body.blocks[0].ops:
                if isinstance(op, (DecodeOp, SelectOp)):
                    discovered.add(resolve_callback(op.callee.root_reference.data).source)
                if isinstance(op, CallOp):
                    discovered.update(uses[op.callee.root_reference.data])
                if isinstance(op, SelectOp):
                    for case in op.cases.data.values():
                        discovered.update(uses[case.root_reference.data])
            if discovered != uses[name]:
                uses[name] = discovered
                changed = True
    return uses


def _host_sequence(kernel: KernelOp, nodes_by_op: dict[int, str], sources: dict[str, set[str]]) -> dict[str, tuple[str, ...]]:
    sequence: dict[str, list[str]] = defaultdict(list)
    for index, op in enumerate(kernel.body.blocks[0].ops):
        used: set[str] = set()
        if isinstance(op, (DecodeOp, SelectOp)):
            used.add(resolve_callback(op.callee.root_reference.data).source)
        if isinstance(op, CallOp):
            used.update(sources[op.callee.root_reference.data])
        if isinstance(op, SelectOp):
            for case in op.cases.data.values():
                used.update(sources[case.root_reference.data])
        for source in used:
            sequence[source].append(nodes_by_op[index])
    return {name: tuple(ids) for name, ids in sequence.items()}


def check_witness_structure(source_module: ModuleOp, target_module: ModuleOp, witness: Witness) -> None:
    """Check both module projections without trusting the compiler's records."""
    if witness.source_width != 1 or witness.target_width != 1:
        raise UnsupportedWitnessError("only identity encoding is implemented")
    source_kernels = _kernels(source_module)
    target_kernels = _kernels(target_module)
    _require(set(source_kernels) == set(target_kernels), "kernel symbols changed without a claim")
    source_declarations = _declarations(source_module)
    target_declarations = _declarations(target_module)
    _require(set(source_declarations) == set(target_declarations), "callback declarations changed without a claim")
    for name in source_declarations:
        old, new = source_declarations[name], target_declarations[name]
        _require(old.name == new.name and old.attributes == new.attributes and old.properties == new.properties, f"callback declaration @{name} changed")

    rules = _unique(witness.rules, "rule")
    nodes = _unique(witness.nodes, "node")
    edges = _unique(witness.edges, "edge")
    _require(
        set(rules) == {node.rule for node in nodes.values() if node.kind == "rule"},
        "rule definitions do not match rule applications",
    )
    boundaries = {item.name: item for item in witness.kernels}
    _require(len(boundaries) == len(witness.kernels) and set(boundaries) == set(source_kernels), "kernel boundaries are incomplete")
    _require(all(node.kernel in source_kernels for node in nodes.values()), "node names unknown kernel")
    _require(all(edge.kernel in source_kernels for edge in edges.values()), "edge names unknown kernel")

    source_host_uses = _callback_sources(source_module)
    target_host_uses = _callback_sources(target_module)
    for name, old_kernel in source_kernels.items():
        new_kernel = target_kernels[name]
        old_side, new_side = _KernelSide(old_kernel), _KernelSide(new_kernel)
        _require(
            old_kernel.input_types == new_kernel.input_types
            and old_kernel.declared_result_types == new_kernel.declared_result_types
            and old_kernel.allocation_count == new_kernel.allocation_count
            and old_kernel.attributes == new_kernel.attributes,
            f"kernel @{name} signature or allocation changed under identity encoding",
        )
        local_nodes = [node for node in nodes.values() if node.kernel == name]
        local_edges = {key: edge for key, edge in edges.items() if edge.kernel == name}
        source_coverage: dict[int, str] = {}
        target_coverage: dict[int, str] = {}
        producers: Counter[str] = Counter(boundaries[name].inputs)
        consumers: Counter[str] = Counter()
        _require(len(boundaries[name].inputs) == len(old_kernel.input_types), f"@{name}: wrong input boundary arity")
        for index, edge_id in enumerate(boundaries[name].inputs):
            _require(edge_id in local_edges, f"@{name}: unknown input edge {edge_id}")
            edge = local_edges[edge_id]
            _require(edge.source == (ValueRef("arg", old_kernel.allocation_count + index),), f"@{name}: source input edge differs")
            _require(edge.target == (ValueRef("arg", new_kernel.allocation_count + index),), f"@{name}: target input edge differs")

        for edge in local_edges.values():
            _require(len(edge.source) == len(edge.target) == 1, f"{edge.id}: identity edge must pair one value")
            _require(old_side.value(edge.source[0]).type == new_side.value(edge.target[0]).type, f"{edge.id}: edge types differ")

        allocation_source: set[int] = set()
        allocation_target: set[int] = set()
        for node in local_nodes:
            _require(all(edge_id in local_edges for edge_id in (*node.inputs, *node.outputs)), f"{node.id}: unknown or cross-kernel edge")
            for index in node.source_ops:
                _require(index not in source_coverage, f"@{name}: source operation {index} covered twice")
                source_coverage[index] = node.id
            for index in node.target_ops:
                _require(index not in target_coverage, f"@{name}: target operation {index} covered twice")
                target_coverage[index] = node.id
            consumers.update(node.inputs)
            producers.update(node.outputs)
            if node.kind == "allocation":
                _require(not node.source_ops and not node.target_ops and not node.inputs and len(node.outputs) == 1, f"{node.id}: malformed allocation")
                edge = local_edges[node.outputs[0]]
                source_ref, target_ref = edge.source[0], edge.target[0]
                _require(source_ref.kind == target_ref.kind == "arg", f"{node.id}: allocation does not bind arguments")
                _require(source_ref.index < old_kernel.allocation_count and target_ref.index < new_kernel.allocation_count, f"{node.id}: allocation binds borrowed input")
                allocation_source.add(source_ref.index)
                allocation_target.add(target_ref.index)
                continue
            _check_region(node, old_side, local_edges, "source")
            _check_region(node, new_side, local_edges, "target")
            if node.kind == "identity":
                _require(node.rule is None, f"{node.id}: identity refers to a circuit rule")
                _check_identity(node, old_side, new_side, local_edges)
            elif node.kind == "rule":
                _require(bool(node.source_ops), f"{node.id}: circuit rule has no source operations")
                _require(node.rule in rules, f"{node.id}: unknown circuit rule")
                _require(
                    _same_circuit(_circuit_at(node, old_side, local_edges, "source"), rules[node.rule].source)
                    and _same_circuit(_circuit_at(node, new_side, local_edges, "target"), rules[node.rule].target),
                    f"{node.id}: site does not instantiate rule {node.rule}",
                )
            else:
                raise UnsupportedWitnessError(f"{node.id}: unknown claim kind {node.kind!r}")

        _require(set(source_coverage) == set(range(len(old_side.ops))), f"@{name}: source operation coverage is incomplete")
        _require(set(target_coverage) == set(range(len(new_side.ops))), f"@{name}: target operation coverage is incomplete")
        _require(all(count == 1 for count in producers.values()) and set(producers) == set(local_edges), f"@{name}: each edge needs one producer")
        _require(all(count == 1 for count in consumers.values()) and set(consumers) == set(local_edges), f"@{name}: each edge needs one consumer")
        _require(allocation_source == set(range(old_kernel.allocation_count)) and allocation_target == set(range(new_kernel.allocation_count)), f"@{name}: allocation claims are incomplete")
        _require(
            _host_sequence(old_kernel, source_coverage, source_host_uses)
            == _host_sequence(new_kernel, target_coverage, target_host_uses),
            f"@{name}: callback host-wire order differs",
        )
