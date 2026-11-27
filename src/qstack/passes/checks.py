"""Validate the construction records produced by compiler passes.

These checks account for source operations and connect target fragments
according to the declared encoding; they do not prove semantic equivalence.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from xdsl.ir import Operation, SSAValue

from qstack.dialect.core import KernelOp, QubitType

if TYPE_CHECKING:
    from qstack.encoding import Encoding
    from qstack.passes.contracts import QubitGroup, Replacement


class PassStructureError(Exception):
    """Raised when a pass's structural replacement contract is not satisfied."""


def _flatten_representation(
    values: Sequence[SSAValue | QubitGroup],
) -> tuple[SSAValue, ...]:
    """Expand target qubit groups for structural type and wiring checks."""
    return tuple(
        qubit
        for value in values
        for qubit in ((value,) if isinstance(value, SSAValue) else value.qubits)
    )


def check_value_pairs(
    pairs: Sequence[tuple[SSAValue, SSAValue | QubitGroup]],
    encoding: Encoding,
) -> None:
    """Check scalar types and qubit-group widths against the encoding."""
    for source_value, target_value in pairs:
        expected_types = encoding.map_types((source_value.type,))
        actual_types = tuple(
            value.type for value in _flatten_representation((target_value,))
        )
        expects_group = (
            isinstance(source_value.type, QubitType) and not encoding.is_identity
        )
        if (not isinstance(target_value, SSAValue)) != expects_group:
            kind = "a qubit group" if expects_group else "a scalar value"
            raise PassStructureError(
                f"replacement for {source_value!r} must be {kind}"
            )
        if actual_types != expected_types:
            raise PassStructureError(
                f"replacement for {source_value!r} has types {actual_types}, "
                f"expected {expected_types}"
            )


def check_replacement(
    replacement: Replacement,
    preceding: dict[SSAValue, SSAValue | QubitGroup],
    encoding: Encoding,
) -> None:
    """Check a fragment's boundary correspondence and detached target wiring."""
    check_value_pairs((*replacement.inputs, *replacement.outputs), encoding)
    for source_value, target_value in replacement.inputs:
        if preceding.get(source_value) != target_value:
            raise PassStructureError(
                "replacement input disagrees with the preceding boundary"
            )

    available = set(
        _flatten_representation(tuple(value for _, value in replacement.inputs))
    )
    seen: set[Operation] = set()
    for operation in replacement.target_operations:
        if operation.parent is not None:
            raise PassStructureError(
                f"replacement operation {operation.name} is already attached"
            )
        if operation in seen:
            raise PassStructureError(
                "replacement contains a duplicate target operation"
            )
        if operation.regions:
            raise PassStructureError(
                "replacement operations cannot contain nested regions"
            )
        if any(value not in available for value in operation.operands):
            raise PassStructureError(
                "target operation uses a value outside its replacement boundary"
            )
        available.update(operation.results)
        seen.add(operation)
    if any(
        value not in available
        for value in _flatten_representation(
            tuple(value for _, value in replacement.outputs)
        )
    ):
        raise PassStructureError(
            "replacement output is not defined by its inputs or target operations"
        )


def check_replacements(
    source: KernelOp,
    snapshot: KernelOp,
    replacements: Sequence[Replacement],
    inputs: dict[SSAValue, SSAValue | QubitGroup],
    encoding: Encoding,
) -> None:
    """Check that lowering left the source intact and covered its body exactly.

    Source fragments must reconstruct the original body in order.  An input
    enters a fragment from outside it; an output is a result used outside it
    or an unused terminal result.  Internal wires need no correspondence.
    """
    if not source.is_structurally_equivalent(snapshot) or any(
        tuple(op.result_types) != tuple(saved.result_types)
        for op, saved in zip(source.walk(), snapshot.walk(), strict=True)
    ):
        raise PassStructureError("body lowering modified the source kernel")
    operations = tuple(source.body.block.ops)
    covered = tuple(op for r in replacements for op in r.source_operations)
    if covered != tuple(operations):
        raise PassStructureError(
            "replacements must cover the source body exactly once in order"
        )
    preceding = dict(inputs)
    target_operations: set[Operation] = set()
    for replacement in replacements:
        members = set(replacement.source_operations)
        if not members:
            raise PassStructureError(
                "body replacement must identify source operations"
            )
        boundary_inputs = tuple(
            dict.fromkeys(
                value
                for operation in replacement.source_operations
                for value in operation.operands
                if value.owner not in members
            )
        )
        boundary_outputs = tuple(
            value
            for operation in replacement.source_operations
            for value in operation.results
            if not value.uses
            or any(use.operation not in members for use in value.uses)
        )
        if tuple(value for value, _ in replacement.inputs) != boundary_inputs:
            raise PassStructureError(
                "replacement inputs do not match the source fragment boundary"
            )
        if tuple(value for value, _ in replacement.outputs) != boundary_outputs:
            raise PassStructureError(
                "replacement outputs do not match the source fragment boundary"
            )
        if target_operations.intersection(replacement.target_operations):
            raise PassStructureError(
                "target operation belongs to multiple replacements"
            )
        check_replacement(replacement, preceding, encoding)
        target_operations.update(replacement.target_operations)
        preceding.update(replacement.outputs)
