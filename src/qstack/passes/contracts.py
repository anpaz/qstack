"""Shared value representations and replacement contracts for compiler passes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from xdsl.ir import Attribute, Operation, SSAValue

from qstack.dialect import QubitType


# An SSA handle whose qstack IR type is ``!qstack.qubit``.
Qubit: TypeAlias = SSAValue[QubitType]


@dataclass(frozen=True)
class QubitGroup:
    """The target SSA values that jointly represent one source qubit.

    For a non-identity encoding, the lowering engine maps a source qubit to a
    group and passes that group to operation handlers.  A repetition-code
    lowering therefore receives three target qubits as one ``QubitGroup`` when
    lowering a gate on one source qubit.

    A group is bookkeeping for a single pass run.  It is not an IR value and is
    never stored in the output module; a later pass sees the emitted target
    qubits and builds its own mappings.
    """

    qubits: tuple[Qubit, ...]


@dataclass(frozen=True)
class KernelSignature:
    """The signature a source kernel will have after the current lowering.

    The engine derives these types from the pass's encoding before it
    lowers any kernel bodies.  Keeping all target signatures up front lets a
    call be rebuilt correctly even when its callee appears later in the module
    or is recursive.  ``inputs`` contains the borrowed kernel inputs, which are
    also the kernel's entry-block arguments.
    """

    inputs: tuple[Attribute, ...]
    results: tuple[Attribute, ...]


@dataclass(frozen=True)
class Replacement:
    """A source fragment, its target implementation, and their shared boundary.

    ``source_operations`` identifies the original operations covered by this
    transformation.  ``target_operations`` contains detached operations in
    execution order, ready for the kernel driver to append.  A fragment may
    cover one operation, an optimization such as ``S;S``, or a whole body.

    ``inputs`` and ``outputs`` pair each source boundary value with its target
    representation.  Bits and identity-encoded qubits have scalar partners;
    other qubits have a ``QubitGroup`` whose width is defined by the encoding.
    Internal source results have no boundary entry.  An unused terminal result
    is still an output, so single-operation replacements cover every result.

    Cancelling ``H;H`` has no target operations and pairs the second H result
    with the target input.  A source ``qstack.alloc`` has no inputs: its
    replacement holds the target allocations and any preparation of encoded
    zero, and its one output is the prepared representation.

    These records describe construction only.  They retain the two regions
    and boundary correspondence needed for future claims, without asserting
    semantic equivalence.
    """

    source_operations: tuple[Operation, ...]
    target_operations: tuple[Operation, ...]
    inputs: tuple[tuple[SSAValue, SSAValue | QubitGroup], ...]
    outputs: tuple[tuple[SSAValue, SSAValue | QubitGroup], ...]
