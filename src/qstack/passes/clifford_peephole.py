"""Simplify adjacent canonical Clifford gates without changing representation.

The optimizer recognizes ``H;H``, ``X;X``, ``Y;Y``, and ``Z;Z`` as identity,
and replaces ``S;S`` with ``Z``.  A pair must be adjacent in the kernel body,
have the same operation type, and form a direct SSA chain on one qubit.  Gates
with attributes or properties are left intact because that metadata may carry
meaning beyond the unitary identity.

Each kernel is rebuilt in one source-order, non-overlapping sweep.  Newly
created opportunities are handled by a later invocation rather than revisited
during the same pass.
"""

from __future__ import annotations

from collections.abc import Sequence

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Operation, SSAValue

from qstack.dialect.cliffords import HOp, SOp, XOp, YOp, ZOp
from qstack.passes.base import LoweringContext, OptimizationPass, QubitGroup, Replacement


class CliffordPeepholeOptimization(OptimizationPass):
    """Rebuild a module while simplifying disjoint pairs of Clifford gates.

    This is an optimization pass, so its encoding remains the identity: kernel
    signatures, allocations, and the number of represented qubits do not
    change.  Removing a cancelling pair forwards its incoming SSA value to the
    second gate's result.  Replacing ``S;S`` emits a fresh ``Z`` result instead.

    Matching is intentionally local.  The pass does not commute gates, cross
    intervening operations, combine gates on different wires, or search again
    after a replacement.
    """

    pass_id = "qstack.clifford-peephole"

    _CANCEL = (HOp, XOp, YOp, ZOp)

    @staticmethod
    def _matches(first, second) -> bool:
        """Return whether two adjacent operations form a supported clean pair.

        A clean pair has one operand and result per operation, uses the same
        supported gate type, carries no attributes or properties, and connects
        the first result directly to the second operand.
        """
        if type(first) is not type(second) or not isinstance(first, (*CliffordPeepholeOptimization._CANCEL, SOp)):
            return False
        if first.attributes or second.attributes or first.properties or second.properties:
            return False
        return (
            len(first.operands) == len(first.results) == 1
            and len(second.operands) == len(second.results) == 1
            and second.operands[0] is first.results[0]
        )

    def lower_body(
        self,
        operations: Sequence[Operation],
        inputs: tuple[tuple[SSAValue, SSAValue | QubitGroup], ...],
        context: LoweringContext,
    ) -> list[Replacement]:
        """Describe each matched pair and preserved operation as a replacement.

        A pair exposes only the first gate's input and the second gate's result;
        its intermediate wire is internal.  Cancellation forwards the mapped
        input, while ``S;S`` creates one detached Z.  The local correspondence
        then connects later fragments to that output.  The kernel driver checks
        all records and assembles the target without modifying the source.
        """
        value_map = dict(inputs)
        replacements = []
        index = 0
        while index < len(operations):
            first = operations[index]
            if index + 1 < len(operations):
                second = operations[index + 1]
                if self._matches(first, second):
                    incoming = value_map[first.operands[0]]
                    assert isinstance(incoming, SSAValue)
                    if isinstance(first, SOp):
                        z = ZOp(incoming)
                        z.location = first.location
                        z.result.name_hint = second.results[0].name_hint
                        target_operations = (z,)
                        output = z.result
                    else:
                        target_operations = ()
                        output = incoming
                    replacement = Replacement(
                        source_operations=(first, second),
                        target_operations=target_operations,
                        inputs=((first.operands[0], incoming),),
                        outputs=((second.results[0], output),),
                    )
                    replacements.append(replacement)
                    value_map.update(replacement.outputs)
                    index += 2
                    continue

            # Unmatched operations still get explicit preservation records.
            preserved = super().lower_body((first,), tuple(value_map.items()), context)
            replacements.extend(preserved)
            value_map.update(preserved[0].outputs)
            index += 1
        return replacements


def optimize_cliffords(module: ModuleOp) -> ModuleOp:
    """Return a fresh module after one non-overlapping Clifford peephole sweep.

    The input module is not modified.  Invoke this function again when
    replacements from the first sweep should participate in further matches.
    """
    return CliffordPeepholeOptimization().run(module)
