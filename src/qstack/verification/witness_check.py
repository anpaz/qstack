"""Independently match both expansions of a witness's claim graph."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Operation, SSAValue

from qstack.callbacks import resolve_callback
from qstack.dialect.core import DecoderOp, KernelOp, SelectorOp
from qstack.verification.model import Claim, Edge, Pattern, Rule, ValueRef, Witness
from qstack.verification.patterns import extract_pattern, operation_sources


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


def _values(
    claim: Claim, edges: dict[str, Edge], side: _KernelSide,
    projection: str, *, output: bool,
) -> tuple[SSAValue, ...]:
    ids = claim.outputs if output else claim.inputs
    return tuple(side.value(ref) for edge_id in ids for ref in getattr(edges[edge_id], projection))


def _pattern_at(
    claim: Claim, side: _KernelSide, edges: dict[str, Edge],
    projection: str, sources: dict[str, set[str]],
) -> Pattern:
    indices = getattr(claim, projection + "_ops")
    inputs = _values(claim, edges, side, projection, output=False)
    outputs = _values(claim, edges, side, projection, output=True)
    _require(len(set(inputs)) == len(inputs), f"{claim.id}: duplicate input value")
    _require(len(set(outputs)) == len(outputs), f"{claim.id}: duplicate output value")
    actual_inputs, actual_outputs = side.region_boundary(indices)
    declared_inputs, declared_outputs = set(inputs), set(outputs)
    _require(actual_inputs <= declared_inputs, f"{claim.id}: uncovered {projection} input")
    _require(actual_outputs <= declared_outputs, f"{claim.id}: uncovered {projection} output")
    forwarded = declared_inputs - actual_inputs
    _require(forwarded == declared_outputs - actual_outputs, f"{claim.id}: invalid {projection} forwarding")
    _require(not (actual_inputs & declared_outputs), f"{claim.id}: consumed {projection} input was forwarded")
    _require(not (actual_outputs & declared_inputs), f"{claim.id}: internal {projection} output is also an input")
    try:
        return extract_pattern(side.kernel, indices, inputs, outputs, sources)
    except (TypeError, ValueError) as exc:
        raise WitnessError(f"{claim.id}: {projection} pattern: {exc}") from exc


def _callback_sources(module: ModuleOp) -> dict[str, set[str]]:
    kernels = _kernels(module)
    uses: dict[str, set[str]] = {name: set() for name in kernels}
    changed = True
    while changed:
        changed = False
        for name, kernel in kernels.items():
            discovered = set(uses[name])
            for op in kernel.body.block.ops:
                discovered.update(operation_sources(op, uses))
            if discovered != uses[name]:
                uses[name] = discovered
                changed = True
    return uses


def _host_sequence(
    kernel: KernelOp, claims_by_op: dict[int, Claim], rules: dict[str, Rule],
    sources: dict[str, set[str]], *, source_side: bool,
) -> dict[str, tuple[str, ...]]:
    sequence: dict[str, list[str]] = defaultdict(list)
    for index, op in enumerate(kernel.body.block.ops):
        claim = claims_by_op[index]
        rule = rules[claim.rule]
        if source_side and rule.kind == "inline":
            # Expand the call's host action to the exact copied body. Repeated
            # claim IDs are intentional: they also detect foreign interleaving.
            for copied in rule.target.operations:
                for host in copied.hosts:
                    sequence[host].append(claim.id)
        else:
            for host in operation_sources(op, sources):
                sequence[host].append(claim.id)
    return {host: tuple(ids) for host, ids in sequence.items()}


def _check_acyclic(
    claims: list[Claim], boundaries: tuple[str, ...], hosts: dict[str, tuple[str, ...]],
) -> None:
    """Check the whole contraction, including implicit host dependencies."""
    producers = {edge: claim.id for claim in claims for edge in claim.outputs}
    successors: dict[str, set[str]] = {claim.id: set() for claim in claims}
    incoming = {claim.id: 0 for claim in claims}

    def connect(before: str, after: str) -> None:
        _require(before != after, f"claim graph contains a self-cycle at {before}")
        if after not in successors[before]:
            successors[before].add(after)
            incoming[after] += 1

    for claim in claims:
        for edge in claim.inputs:
            if edge not in boundaries:
                connect(producers[edge], claim.id)
    for sequence in hosts.values():
        for before, after in zip(sequence, sequence[1:]):
            if before != after:
                connect(before, after)
    ready = [claim for claim, count in incoming.items() if count == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for following in successors[current]:
            incoming[following] -= 1
            if incoming[following] == 0:
                ready.append(following)
    _require(visited == len(claims), "claim graph is cyclic")


def check_witness_structure(source_module: ModuleOp, target_module: ModuleOp, witness: Witness) -> None:
    """Check coverage, bindings, and graph expansions independently of rules."""
    encoding = witness.encoding
    encoded = not encoding.is_identity

    source_kernels, target_kernels = _kernels(source_module), _kernels(target_module)
    _require(set(source_kernels) == set(target_kernels), "kernel symbols changed without a claim")
    source_declarations, target_declarations = _declarations(source_module), _declarations(target_module)
    _require(source_declarations.keys() <= target_declarations.keys(), "source callback declaration removed")
    added = target_declarations.keys() - source_declarations.keys()
    _require(not added or encoded, "callback declarations changed without a claim")
    existing_sources = {resolve_callback(name).source for name in source_declarations}
    for name in added:
        if not isinstance(target_declarations[name], DecoderOp):
            raise UnsupportedWitnessError("only introduced decoders are supported for encoded gates")
        _require(resolve_callback(name).source not in existing_sources, f"@{name}: callback source is not fresh")
    for name, old in source_declarations.items():
        new = target_declarations[name]
        _require(old.name == new.name and old.attributes == new.attributes and old.properties == new.properties, f"callback declaration @{name} changed")
    rules = _unique(witness.rules, "rule")
    claims = _unique(witness.claims, "claim")
    edges = _unique(witness.edges, "edge")
    _require(set(rules) == {claim.rule for claim in claims.values()}, "rule definitions do not match claim applications")
    boundaries = {item.name: item for item in witness.kernels}
    _require(len(boundaries) == len(witness.kernels) and set(boundaries) == set(source_kernels), "kernel boundaries are incomplete")
    _require(all(claim.kernel in source_kernels for claim in claims.values()), "claim names unknown kernel")
    _require(all(edge.kernel in source_kernels for edge in edges.values()), "edge names unknown kernel")
    source_hosts, target_hosts = _callback_sources(source_module), _callback_sources(target_module)

    for name, old_kernel in source_kernels.items():
        new_kernel = target_kernels[name]
        old_side, new_side = _KernelSide(old_kernel), _KernelSide(new_kernel)
        _require(encoding.map_types(old_kernel.input_types) == tuple(new_kernel.input_types)
                 and encoding.map_types(old_kernel.declared_result_types) == tuple(new_kernel.declared_result_types)
                 and old_kernel.attributes == new_kernel.attributes, f"@{name}: kernel signature or attributes changed")
        local_claims = [claim for claim in claims.values() if claim.kernel == name]
        local_edges = {key: edge for key, edge in edges.items() if edge.kernel == name}
        producers: Counter[str] = Counter(boundaries[name].inputs)
        consumers: Counter[str] = Counter()
        coverage: dict[str, dict[int, Claim]] = {"source": {}, "target": {}}
        _require(len(boundaries[name].inputs) == len(old_kernel.input_types), f"@{name}: wrong input boundary arity")
        offset = 0
        for index, edge_id in enumerate(boundaries[name].inputs):
            _require(edge_id in local_edges, f"@{name}: unknown input edge {edge_id}")
            edge = local_edges[edge_id]
            _require(edge.source == (ValueRef("arg", index),), f"@{name}: source input edge differs")
            count = len(encoding.map_types((old_kernel.input_types[index],)))
            _require(edge.target == tuple(ValueRef("arg", i) for i in range(offset, offset + count)), f"@{name}: target input edge differs")
            offset += count
        for edge in local_edges.values():
            _require(len(edge.source) == 1, f"{edge.id}: expected one source value")
            typ = old_side.value(edge.source[0]).type
            _require(tuple(new_side.value(ref).type for ref in edge.target) == encoding.map_types((typ,)), f"{edge.id}: edge types differ")
        for claim in local_claims:
            _require(all(edge in local_edges for edge in (*claim.inputs, *claim.outputs)), f"{claim.id}: unknown or cross-kernel edge")
            producers.update(claim.outputs)
            consumers.update(claim.inputs)
            for projection, side, host_uses in (("source", old_side, source_hosts), ("target", new_side, target_hosts)):
                for index in getattr(claim, projection + "_ops"):
                    _require(index not in coverage[projection], f"@{name}: {projection} operation {index} covered twice")
                    coverage[projection][index] = claim
                actual = _pattern_at(claim, side, local_edges, projection, host_uses)
                _require(actual == getattr(rules[claim.rule], projection), f"{claim.id}: {projection} site does not instantiate rule {claim.rule}")
        for projection, side in (("source", old_side), ("target", new_side)):
            _require(set(coverage[projection]) == set(range(len(side.ops))), f"@{name}: {projection} operation coverage is incomplete")
        _require(all(count == 1 for count in producers.values()) and set(producers) == set(local_edges), f"@{name}: each edge needs one producer")
        _require(all(count == 1 for count in consumers.values()) and set(consumers) == set(local_edges), f"@{name}: each edge needs one consumer")
        old_hosts = _host_sequence(old_kernel, coverage["source"], rules, source_hosts, source_side=True)
        new_hosts = _host_sequence(new_kernel, coverage["target"], rules, target_hosts, source_side=False)
        if encoded:
            # New decoder uses belong to the as-yet unchecked measurement rules.
            _check_acyclic(local_claims, boundaries[name].inputs, new_hosts)
            new_hosts = {host: seq for host, seq in new_hosts.items() if host in existing_sources}
        _require(old_hosts == new_hosts, f"@{name}: callback host-wire order differs")
        _check_acyclic(local_claims, boundaries[name].inputs, old_hosts)
