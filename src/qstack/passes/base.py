"""Shared fresh-construction framework for qstack compiler passes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeAlias, cast

from xdsl.dialects.builtin import ArrayAttr, ModuleOp, StringAttr
from xdsl.ir import Attribute, Block, Operation, Region, SSAValue

from qstack.dialect import QubitType
from qstack.dialect.core import (
    CallOp,
    DecodeOp,
    DecoderOp,
    KernelOp,
    MeasureOp,
    ReturnOp,
    SelectOp,
    SelectorOp,
)
from qstack.verifier import (
    PASS_HISTORY_ATTR,
    PassStructureError,
    check_replacement,
    check_replacements,
    check_value_pairs,
    verify_module,
)


class PassError(Exception):
    """Raised when a qstack pass cannot transform its input."""


@dataclass(frozen=True)
class Encoding:
    """Declare the qubit representation promised by a lowering.

    ``Encoding(1, 3)``, for example, means that every qubit visible to the
    source program is represented by three qubits in the target program.  The
    lowering engine uses this declaration to widen kernel arguments, results,
    and allocations, and to decide whether an operation handler receives a
    single target SSA value or a :class:`QubitGroup`.

    The widths are the structural part of that promise.  The pass realizes it
    by implementing :meth:`LoweringPass.prepare_encoded_zero` and its operation
    handlers.  The preparation must produce the encoded image of logical
    ``|0>``; each handler must implement its source operation on encoded values.
    A future isometry artifact will complete the semantic declaration and let a
    verifier check both kinds of implementation against the same encoding.

    The engine currently implements only ``source_width == 1`` because its
    value map starts from one source SSA value at a time.  ``target_width`` may
    be any positive width.  Bits and other non-qubit values always remain one
    scalar SSA value.
    """

    source_width: int = 1
    target_width: int = 1

    @classmethod
    def identity(cls) -> "Encoding":
        return cls()

    @property
    def is_identity(self) -> bool:
        return self.source_width == self.target_width == 1

    def map_types(self, source_types: Sequence[Attribute]) -> tuple[Attribute, ...]:
        if self.is_identity:
            return tuple(source_types)
        if self.source_width != 1:
            raise PassError(
                "the lowering engine currently supports only one source qubit "
                "per encoding unit"
            )
        target_types: list[Attribute] = []
        for source_type in source_types:
            if isinstance(source_type, QubitType):
                target_types.extend(QubitType() for _ in range(self.target_width))
            else:
                target_types.append(source_type)
        return tuple(target_types)


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

    The engine derives these types from the pass's :class:`Encoding` before it
    lowers any kernel bodies.  Keeping all target signatures up front lets a
    call be rebuilt correctly even when its callee appears later in the module
    or is recursive.  ``inputs`` contains the borrowed kernel inputs; fresh
    allocations are entry-block arguments but are not part of this tuple.
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
    with the target input.  Allocation preparation has no source operations:
    its input and output pairs refer to the same fresh source argument, before
    and after preparation.  The kernel driver handles it outside ``lower_body``.

    These records describe construction only.  They retain the two regions
    and boundary correspondence needed for future claims, without asserting
    semantic equivalence.
    """

    source_operations: tuple[Operation, ...]
    target_operations: tuple[Operation, ...]
    inputs: tuple[tuple[SSAValue, SSAValue | QubitGroup], ...]
    outputs: tuple[tuple[SSAValue, SSAValue | QubitGroup], ...]


@dataclass
class LoweringContext:
    """Mutable workspace shared while one pass invocation builds its module.

    The engine creates a fresh context for every call to ``LoweringPass.run``.
    ``history`` records the passes already applied to the source module;
    ``pass_index`` derives this invocation's next position from that history.
    ``signatures`` contains the target signature of every source kernel.  A
    pass may add declarations to ``compiler_callbacks``, helper kernels to
    ``helper_kernels``, and private run data to ``data`` while preparing the
    context.

    ``current_kernel`` identifies the kernel currently being lowered so pass
    diagnostics can name it.  The source-to-target value map is intentionally
    local to the kernel builder and is not exposed to handlers through this
    run-wide context.
    """

    history: tuple[str, ...]
    signatures: dict[StringAttr, KernelSignature]
    compiler_callbacks: dict[str, SelectorOp | DecoderOp] = field(default_factory=dict)
    helper_kernels: list[KernelOp] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    current_kernel: str | None = None

    @property
    def pass_index(self) -> int:
        """Return the one-based history position of the pass being run."""
        return len(self.history) + 1

Handler: TypeAlias = Callable[
    [Operation, tuple[SSAValue | QubitGroup, ...], LoweringContext],
    tuple[Sequence[Operation], Sequence[SSAValue | QubitGroup]],
]


def copy_operation_metadata(source: Operation, target: Operation) -> None:
    """Copy generic attributes, location, and result hints onto a changed operation."""
    target.attributes.update(source.attributes)
    target.location = source.location
    for old_result, new_result in zip(source.results, target.results):
        new_result.name_hint = old_result.name_hint


class LoweringPass:
    """Engine for constructing a new module from operation-level handlers.

    A subclass declares an :class:`Encoding`, registers any generated module
    artifacts in :meth:`prepare_run`, and provides handlers for the operations
    it changes.  The engine derives target signatures, creates new kernel
    blocks, and checks the :class:`Replacement` records returned by
    :meth:`lower_body`.  Operation handlers return target operations and outputs;
    the default body hook supplies their source regions and boundary mappings.
    It never mutates or reuses operations from the source module.
    """

    preserve_unhandled_operations = True
    encoding = Encoding.identity()
    pass_id: str | None = None

    def run(self, module: ModuleOp) -> ModuleOp:
        verify_module(module)

        context = self.prepare_run(module)

        target_ops: list[Operation] = []
        for op in module.body.ops:
            if isinstance(op, DecoderOp):
                target_ops.append(self._lower_decoder(op, context))
            elif isinstance(op, SelectorOp):
                target_ops.append(self._lower_selector(op, context))
            elif isinstance(op, KernelOp):
                target_ops.append(self._lower_kernel(op, context))
            else:  # pragma: no cover - input verification rejects this
                raise self.error(context, f"unsupported top-level operation {op.name}")
        target_ops.extend(context.compiler_callbacks.values())
        target_ops.extend(context.helper_kernels)

        attributes = dict(module.attributes)
        attributes[PASS_HISTORY_ATTR] = ArrayAttr(
            [
                *(StringAttr(entry) for entry in context.history),
                StringAttr(self.pass_id),
            ]
        )
        output = ModuleOp(
            target_ops,
            attributes=attributes,
            sym_name=module.properties.get("sym_name"),
        )
        output.location = module.location
        output.verify()
        verify_module(output)
        return output

    def prepare_run(self, module: ModuleOp) -> LoweringContext:
        """Analyze the source module and create this invocation's run context."""
        history_attr = module.attributes.get(PASS_HISTORY_ATTR)
        history = (
            ()
            if history_attr is None
            else tuple(entry.data for entry in cast(ArrayAttr[StringAttr], history_attr))
        )
        signatures = {
            op.sym_name: KernelSignature(
                inputs=self.encoding.map_types(tuple(op.input_types)),
                results=self.encoding.map_types(
                    tuple(op.declared_result_types)
                ),
            )
            for op in module.body.ops
            if isinstance(op, KernelOp)
        }
        return LoweringContext(history, signatures)

    def operation_handlers(self) -> dict[type[Operation], Handler]:
        return {}

    def prepare_encoded_zero(
        self,
        target_value: Qubit | QubitGroup,
        context: LoweringContext,
    ) -> tuple[Sequence[Operation], Sequence[SSAValue | QubitGroup]]:
        """Realize logical ``|0>`` in one freshly allocated target representation.

        Kernel allocation supplies physical ``|0>`` qubits.  The default is
        therefore sufficient for the identity encoding and encodings whose
        logical zero is the all-zero target state.  Other encodings override
        this hook and return operations and one output representation for the
        prepared logical zero.  The kernel driver records that boundary.
        """
        return [], (target_value,)

    def error(self, context: LoweringContext, message: str) -> PassError:
        where = "" if context.current_kernel is None else f" in kernel @{context.current_kernel}"
        return PassError(f"{type(self).__name__}{where}: {message}")

    def _lower_decoder(
        self,
        source: DecoderOp,
        context: LoweringContext,
    ) -> Operation:
        """Copy an existing decoder declaration into the target module."""
        return source.clone()

    def _lower_selector(
        self,
        source: SelectorOp,
        context: LoweringContext,
    ) -> Operation:
        """Copy an existing selector declaration into the target module."""
        return source.clone()

    def _lower_kernel(self, source: KernelOp, context: LoweringContext) -> KernelOp:
        """Prepare a kernel boundary, obtain body replacements, and assemble them."""
        context.current_kernel = source.sym_name.data
        signature = context.signatures[source.sym_name]
        source_snapshot = source.clone()
        source_operations = tuple(source.body.block.ops)

        # Entry values belong to the new kernel.  The encoding determines which
        # of them jointly represent each source argument.
        entry_types = self.encoding.map_types(
            tuple(argument.type for argument in source.body.block.args)
        )
        target_block = Block(arg_types=entry_types)
        entry_values = self._group_values(
            source.body.block.args, target_block.args, context
        )
        value_map = dict(self._pair_values(source.body.block.args, entry_values, context))

        # Allocations are entry arguments, not body operations.  Prepare their
        # logical zero before handing the entry correspondence to lower_body.
        for source_value in source.body.block.args[: source.allocation_count]:
            incoming = value_map[source_value]
            operations, outputs = self.prepare_encoded_zero(incoming, context)
            preparation = Replacement(
                source_operations=(),
                target_operations=tuple(operations),
                inputs=((source_value, incoming),),
                outputs=self._pair_values((source_value,), outputs, context),
            )
            self._check_and_apply(preparation, target_block, value_map, context)

        replacements = self.lower_body(
            source_operations, tuple(value_map.items()), context
        )
        self._check(
            check_replacements,
            context,
            source,
            source_snapshot,
            replacements,
            value_map,
            self.encoding,
        )
        for replacement in replacements:
            self._apply_replacement(replacement, target_block, value_map)

        # The body hook owns neither the signature nor the allocation boundary.
        target = KernelOp(
            source.sym_name.data,
            input_types=signature.inputs,
            result_types=signature.results,
            allocates=source.allocation_count * self.encoding.target_width,
            region=Region([target_block]),
        )
        target.attributes.update(source.attributes)
        target.location = source.location
        context.current_kernel = None
        return target

    def lower_body(
        self,
        operations: Sequence[Operation],
        inputs: tuple[tuple[SSAValue, SSAValue | QubitGroup], ...],
        context: LoweringContext,
    ) -> list[Replacement]:
        """Describe a body transformation as ordered source/target replacements.

        ``inputs`` pairs source entry values with their prepared target values.
        The default walks the source operations, passes mapped operands to each
        handler, and wraps its returned operations and outputs in a replacement.
        Its local SSA map lets subsequent handlers use earlier target results.

        An override may cover several source operations with one replacement,
        including the entire body.  The returned source fragments must partition
        ``operations`` in order; target fragments must remain detached and use
        only their mapped boundary inputs or earlier results within the fragment.
        The kernel driver checks and attaches them after this method returns.
        """
        value_map = dict(inputs)
        replacements = []
        for source in operations:
            operands = tuple(value_map[value] for value in source.operands)
            target_operations, outputs = self.lower_operation(source, operands, context)
            replacement = Replacement(
                source_operations=(source,),
                target_operations=tuple(target_operations),
                inputs=tuple(dict(zip(source.operands, operands, strict=True)).items()),
                outputs=self._pair_values(source.results, outputs, context),
            )
            replacements.append(replacement)
            value_map.update(replacement.outputs)
        return replacements

    def _check(
        self,
        check: Callable[..., Any],
        context: LoweringContext,
        *args: Any,
    ) -> Any:
        """Report failed structural checks with the current pass and kernel."""
        try:
            return check(*args)
        except PassStructureError as exc:
            raise self.error(context, str(exc)) from exc

    def _pair_values(
        self,
        source_values: Sequence[SSAValue],
        target_values: Sequence[SSAValue | QubitGroup],
        context: LoweringContext,
    ) -> tuple[tuple[SSAValue, SSAValue | QubitGroup], ...]:
        """Pair source values with target representations of the encoded shape."""
        try:
            pairs = tuple(zip(source_values, target_values, strict=True))
        except ValueError as exc:
            raise self.error(
                context,
                f"handler returned {len(target_values)} outputs for "
                f"{len(source_values)} source results",
            ) from exc
        self._check(check_value_pairs, context, pairs, self.encoding)
        return pairs

    def _check_and_apply(
        self,
        replacement: Replacement,
        block: Block,
        value_map: dict[SSAValue, SSAValue | QubitGroup],
        context: LoweringContext,
    ) -> None:
        """Check a complete replacement before committing it to the target kernel."""
        self._check(check_replacement, context, replacement, value_map, self.encoding)
        self._apply_replacement(replacement, block, value_map)

    @staticmethod
    def _apply_replacement(
        replacement: Replacement,
        block: Block,
        value_map: dict[SSAValue, SSAValue | QubitGroup],
    ) -> None:
        """Append a checked target fragment and commit its output correspondence."""
        block.add_ops(replacement.target_operations)
        value_map.update(replacement.outputs)

    def _group_values(
        self,
        source_values: Sequence[SSAValue],
        target_values: Sequence[SSAValue],
        context: LoweringContext,
    ) -> tuple[SSAValue | QubitGroup, ...]:
        """Group flat target IR values according to the source value types."""
        expected_count = len(
            self.encoding.map_types(tuple(value.type for value in source_values))
        )
        if len(target_values) != expected_count:
            raise self.error(
                context,
                f"expected {expected_count} target values, got {len(target_values)}",
            )
        grouped: list[SSAValue | QubitGroup] = []
        cursor = 0
        for source_value in source_values:
            if (
                isinstance(source_value.type, QubitType)
                and not self.encoding.is_identity
            ):
                end = cursor + self.encoding.target_width
                grouped.append(QubitGroup(tuple(target_values[cursor:end])))
                cursor = end
            else:
                grouped.append(target_values[cursor])
                cursor += 1
        return tuple(grouped)

    @staticmethod
    def _flatten(
        values: Sequence[SSAValue | QubitGroup],
    ) -> tuple[SSAValue, ...]:
        return tuple(
            target
            for value in values
            for target in (value.qubits if isinstance(value, QubitGroup) else (value,))
        )

    def lower_operation(
        self,
        source: Operation,
        mapped_operands: tuple[SSAValue | QubitGroup, ...],
        context: LoweringContext,
    ) -> tuple[Sequence[Operation], Sequence[SSAValue | QubitGroup]]:
        """Dispatch one source operation and return target operations and outputs.

        Outputs follow source result order and may forward mapped inputs even
        when no target operation is needed.  The caller wraps this construction
        result with the source operations and boundary pairs in a Replacement.
        """
        handler = self.operation_handlers().get(type(source))
        if handler is not None:
            return handler(source, mapped_operands, context)
        if isinstance(source, MeasureOp):
            return self.lower_measure(source, mapped_operands, context)
        if isinstance(source, DecodeOp):
            return self.lower_decode(source, mapped_operands, context)
        if isinstance(source, CallOp):
            return self.lower_call(source, mapped_operands, context)
        if isinstance(source, SelectOp):
            return self.lower_select(source, mapped_operands, context)
        if isinstance(source, ReturnOp):
            return self.lower_return(source, mapped_operands, context)
        if self.preserve_unhandled_operations:
            return self.preserve_operation(source, mapped_operands, context)
        raise self.error(context, f"unsupported operation {source.name!r}")

    def preserve_operation(
        self,
        source: Operation,
        mapped_operands: tuple[SSAValue | QubitGroup, ...],
        context: LoweringContext,
    ) -> tuple[Sequence[Operation], Sequence[SSAValue | QubitGroup]]:
        """Rebuild an otherwise unhandled operation with its mapped operands.

        Preservation creates a new operation of the same type with the same
        attributes and properties; it never attaches the source operation to
        the target module.  It is valid only when every operand and result is a
        scalar SSA value in the target representation.
        """
        mapper = {
            operand: value
            for operand, value in zip(source.operands, mapped_operands, strict=True)
        }
        target = source.clone_without_regions(mapper)
        return [target], tuple(target.results)

    def lower_measure(
        self,
        source: Operation,
        mapped_operands: tuple[SSAValue | QubitGroup, ...],
        context: LoweringContext,
    ) -> tuple[Sequence[Operation], Sequence[SSAValue | QubitGroup]]:
        target = MeasureOp(operand=mapped_operands[0])
        copy_operation_metadata(source, target)
        return [target], (target.result,)

    def lower_decode(
        self,
        source: Operation,
        mapped_operands: tuple[SSAValue | QubitGroup, ...],
        context: LoweringContext,
    ) -> tuple[Sequence[Operation], Sequence[SSAValue | QubitGroup]]:
        assert isinstance(source, DecodeOp)
        target = DecodeOp(
            callee=source.callee,
            bit_operands=mapped_operands,
        )
        copy_operation_metadata(source, target)
        return [target], (target.result,)

    def lower_call(
        self,
        source: Operation,
        mapped_operands: tuple[SSAValue | QubitGroup, ...],
        context: LoweringContext,
    ) -> tuple[Sequence[Operation], Sequence[SSAValue | QubitGroup]]:
        assert isinstance(source, CallOp)
        callee_signature = context.signatures[source.callee.root_reference]
        target = CallOp(
            source.callee,
            self._flatten(mapped_operands),
            callee_signature.results,
        )
        copy_operation_metadata(source, target)
        return [target], self._group_values(source.results, target.results, context)

    def lower_select(
        self,
        source: Operation,
        mapped_operands: tuple[SSAValue | QubitGroup, ...],
        context: LoweringContext,
    ) -> tuple[Sequence[Operation], Sequence[SSAValue | QubitGroup]]:
        assert isinstance(source, SelectOp)
        bit_count = len(source.bit_operands)
        bits = mapped_operands[:bit_count]
        arguments = mapped_operands[bit_count:]
        result_types = self.encoding.map_types(
            tuple(result.type for result in source.results)
        )
        target = SelectOp(
            callee=source.callee,
            bit_operands=bits,
            cases=dict(source.cases.data),
            case_arguments=self._flatten(arguments),
            result_types=result_types,
        )
        copy_operation_metadata(source, target)
        return [target], self._group_values(source.results, target.results, context)

    def lower_return(
        self,
        source: Operation,
        mapped_operands: tuple[SSAValue | QubitGroup, ...],
        context: LoweringContext,
    ) -> tuple[Sequence[Operation], Sequence[SSAValue | QubitGroup]]:
        target = ReturnOp(operands=self._flatten(mapped_operands))
        copy_operation_metadata(source, target)
        return [target], ()


class OptimizationPass(LoweringPass):
    """Base for fragment replacements that preserve the representation of values.

    Optimizations use the same construction contract as lowerings.  They may
    override ``lower_body`` to replace several source operations at a time,
    returning explicit source/target regions and their boundary correspondence.
    The identity encoding keeps qubits and bits scalar on both sides.
    """


def require_qubit_group(
    value: Qubit | QubitGroup,
    *,
    pass_: LoweringPass,
    context: LoweringContext,
    description: str,
) -> QubitGroup:
    """Return an encoded qubit operand or raise a pass-local diagnostic."""
    if not isinstance(value, QubitGroup):
        raise pass_.error(context, f"expected a qubit group for {description}")
    return value
