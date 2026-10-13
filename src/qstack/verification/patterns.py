"""Extract and normalize concrete rule graphs without trusting a pass."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping, Sequence

from xdsl.ir import Operation, SSAValue

from qstack.callbacks import resolve_callback
from qstack.dialect.core import CallOp, DecodeOp, KernelOp, SelectOp, UnitaryGateOp
from qstack.verification.model import Circuit, Gate, Pattern, PatternOp, ValueRef

QUBIT = "!qstack.qubit"


def operation_sources(op: Operation, sources: Mapping[str, set[str]]) -> tuple[str, ...]:
    used: set[str] = set()
    if isinstance(op, (DecodeOp, SelectOp)):
        used.add(resolve_callback(op.callee.root_reference.data).source)
    if isinstance(op, CallOp):
        used.update(sources[op.callee.root_reference.data])
    if isinstance(op, SelectOp):
        for case in op.cases.data.values():
            used.update(sources[case.root_reference.data])
    return tuple(sorted(used))


def canonical_pattern(pattern: Pattern) -> Pattern:
    """Number graph nodes from ordered outputs, respecting data and host wires.

    Independent operations may appear in either textual order. Following
    producers backwards gives the same numbering in either case, while host
    predecessors retain the order of operations that may share callback state.
    """
    predecessors: dict[int, list[int]] = {}
    last: dict[str, int] = {}
    for index, op in enumerate(pattern.operations):
        predecessors[index] = [last[source] for source in op.hosts if source in last]
        for source in op.hosts:
            last[source] = index
    mapping: dict[int, int] = {}
    operations: list[PatternOp] = []

    def reference(ref: ValueRef) -> None:
        if ref.kind == "arg":
            if ref.slot != 0 or not 0 <= ref.index < len(pattern.inputs):
                raise ValueError("invalid pattern input reference")
        elif ref.kind != "result" or not 0 <= ref.index < len(pattern.operations):
            raise ValueError("invalid pattern operation reference")
        elif not 0 <= ref.slot < len(pattern.operations[ref.index].result_types):
            raise ValueError("invalid pattern result reference")

    def mapped(ref: ValueRef) -> ValueRef:
        return ref if ref.kind == "arg" else ValueRef("result", mapping[ref.index], ref.slot)

    def visit(index: int) -> None:
        visiting: set[int] = set()
        pending = [(index, False)]
        while pending:
            current, expanded = pending.pop()
            if current in mapping:
                continue
            op = pattern.operations[current]
            if expanded:
                mapping[current] = len(operations)
                operations.append(replace(op, operands=tuple(mapped(ref) for ref in op.operands)))
                visiting.remove(current)
                continue
            if current in visiting:
                raise ValueError("cyclic rule pattern")
            visiting.add(current)
            for ref in op.operands:
                reference(ref)
            dependencies = [*predecessors[current], *(ref.index for ref in op.operands if ref.kind == "result")]
            pending.append((current, True))
            pending.extend((dependency, False) for dependency in reversed(dependencies))

    def value(ref: ValueRef) -> ValueRef:
        reference(ref)
        if ref.kind == "result":
            visit(ref.index)
        return mapped(ref)

    outputs = tuple(value(ref) for ref in pattern.outputs)
    # Valid closed regions end in a return; open regions end at output ports.
    for index, op in enumerate(pattern.operations):
        if not op.result_types:
            visit(index)
    if len(mapping) != len(pattern.operations):
        raise ValueError("pattern contains operations disconnected from its outputs")
    return Pattern(pattern.inputs, tuple(operations), outputs)


def extract_pattern(
    kernel: KernelOp,
    indices: Sequence[int],
    inputs: Sequence[SSAValue],
    outputs: Sequence[SSAValue],
    allocations: Sequence[int],
    sources: Mapping[str, set[str]],
) -> Pattern:
    """Read an actual IR fragment as a graph with numbered boundary ports."""
    refs = {value: ValueRef("arg", index) for index, value in enumerate(inputs)}
    operations: list[PatternOp] = []
    for index in allocations:
        argument = kernel.body.block.args[index]
        refs[argument] = ValueRef("result", len(operations))
        operations.append(PatternOp("qstack.alloc", (), (QUBIT,)))
    body = tuple(kernel.body.block.ops)
    for index in indices:
        op = body[index]
        try:
            operands = tuple(refs[value] for value in op.operands)
        except KeyError as exc:
            raise ValueError("pattern operand is outside its boundary") from exc
        gate = Gate.from_op(op, ()) if isinstance(op, UnitaryGateOp) else None
        operations.append(PatternOp(
            op.name, operands, tuple(str(value.type) for value in op.results),
            tuple((name, str(value)) for name, value in sorted(op.properties.items())),
            tuple((name, str(value)) for name, value in sorted(op.attributes.items())),
            gate, operation_sources(op, sources),
        ))
        for slot, value in enumerate(op.results):
            refs[value] = ValueRef("result", len(operations) - 1, slot)
    try:
        result_refs = tuple(refs[value] for value in outputs)
    except KeyError as exc:
        raise ValueError("pattern output is outside its boundary") from exc
    return canonical_pattern(Pattern(tuple(str(value.type) for value in inputs), tuple(operations), result_refs))


def pattern_circuit(pattern: Pattern) -> Circuit:
    """Project a gate-only pattern to the portable circuit backend contract."""
    if any(typ != QUBIT for typ in pattern.inputs):
        raise ValueError("gate rule has non-qubit inputs")
    live = {ValueRef("arg", index): index for index in range(len(pattern.inputs))}
    gates = []
    for index, op in enumerate(pattern.operations):
        if op.gate is None or op.hosts or any(typ != QUBIT for typ in op.result_types):
            raise ValueError("gate rule contains a nonunitary operation")
        if len(op.operands) != len(op.result_types):
            raise ValueError("gate does not thread its wires")
        try:
            wires = tuple(live.pop(ref) for ref in op.operands)
        except KeyError as exc:
            raise ValueError("gate rule consumes an unavailable wire") from exc
        gates.append(replace(op.gate, wires=wires))
        for slot, wire in enumerate(wires):
            live[ValueRef("result", index, slot)] = wire
    if len(pattern.outputs) != len(pattern.inputs) or set(pattern.outputs) != set(live):
        raise ValueError("gate rule output boundary does not preserve its wires")
    # A boundary permutation is part of the rule, not an ignored renaming.
    order = [live[ref] for ref in pattern.outputs]
    swap = (
        ((1., 0.), (0., 0.), (0., 0.), (0., 0.)),
        ((0., 0.), (0., 0.), (1., 0.), (0., 0.)),
        ((0., 0.), (1., 0.), (0., 0.), (0., 0.)),
        ((0., 0.), (0., 0.), (0., 0.), (1., 0.)),
    )
    for desired in range(len(order)):
        actual = order[desired]
        if desired != actual:
            gates.append(Gate("qstack.swap", (desired, actual), (), swap))
            order = [actual if wire == desired else desired if wire == actual else wire for wire in order]
    return Circuit(len(pattern.inputs), tuple(gates))
