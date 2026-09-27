"""IR verification and structural checks for pass construction.

This module enforces the executable shape from :mod:`docs.DESIGN`; it does
not attempt semantic equivalence checking or callback-obligation generation.
The pass checks account for source operations and connect target fragments
according to the declared encoding; they do not prove semantic equivalence.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from xdsl.dialects.builtin import ArrayAttr, ModuleOp, StringAttr, SymbolRefAttr
from xdsl.ir import Operation, SSAValue

from qstack.callbacks import resolve_callback
from qstack.dialect.core import (
    BitType,
    CallOp,
    DecodeOp,
    DecoderOp,
    KernelOp,
    MeasureOp,
    QubitType,
    ReturnOp,
    SelectOp,
    SelectorOp,
    UnitaryGateOp,
)

if TYPE_CHECKING:
    from qstack.passes.base import Encoding, QubitGroup, Replacement

PASS_HISTORY_ATTR = "qstack.pass_history"


class LinearityError(Exception):
    """Raised for any structural or linearity violation in a qstack module."""


class PassStructureError(Exception):
    """Raised when a pass's structural replacement contract is not satisfied."""


def _type_list(values: Iterable[SSAValue]) -> list[object]:
    return [value.type for value in values]


def _check_same_types(actual: Iterable[object], expected: Iterable[object], message: str) -> None:
    if list(actual) != list(expected):
        raise LinearityError(message)


def _symbol_name(ref: SymbolRefAttr) -> str:
    return ref.root_reference.data


def _is_linear(value: SSAValue) -> bool:
    return isinstance(value.type, (QubitType, BitType))


def _check_single_use(value: SSAValue, where: str) -> None:
    uses = list(value.uses)
    if len(uses) != 1:
        qualifier = "unused" if not uses else f"used {len(uses)} times"
        raise LinearityError(f"linear value {value!r} ({value.type}) is {qualifier} at {where}")


def _linear_values(kernel: KernelOp) -> Iterable[SSAValue]:
    block = kernel.body.blocks[0]
    yield from block.args
    for op in block.ops:
        yield from op.results


def _check_kernel_body_ops(kernel: KernelOp) -> None:
    block = kernel.body.blocks[0]
    allowed = (UnitaryGateOp, MeasureOp, DecodeOp, SelectOp, CallOp, ReturnOp)
    for op in block.ops:
        if not isinstance(op, allowed):
            raise LinearityError(f"kernel @{kernel.sym_name.data} contains forbidden operation {op.name}")
        if op.regions:
            raise LinearityError(f"kernel @{kernel.sym_name.data} contains nested region operation {op.name}")
        if isinstance(op, MeasureOp) and not isinstance(op.qubit.type, QubitType):
            raise LinearityError("qstack.measure operand is not a qubit")
        if isinstance(op, (DecodeOp, SelectOp)) and any(
            not isinstance(value.type, BitType) for value in op.bit_operands
        ):
            raise LinearityError(f"{op.name} bit operands must all be bits")


def _check_kernel_shape(kernel: KernelOp) -> None:
    if len(kernel.body.blocks) != 1:
        raise LinearityError(f"kernel @{kernel.sym_name.data} must have exactly one block")
    if kernel.allocation_count < 0:
        raise LinearityError(f"kernel @{kernel.sym_name.data} has a negative allocation count")
    block = kernel.body.blocks[0]
    expected_args = [*[QubitType() for _ in range(kernel.allocation_count)], *kernel.input_types]
    _check_same_types(
        _type_list(block.args),
        expected_args,
        f"kernel @{kernel.sym_name.data} entry arguments do not match its signature and allocations",
    )
    if not isinstance(block.last_op, ReturnOp):
        raise LinearityError(f"kernel @{kernel.sym_name.data} must end in qstack.return")
    _check_same_types(
        _type_list(block.last_op.operands),
        kernel.declared_result_types,
        f"qstack.return in @{kernel.sym_name.data} does not match the declared result types",
    )
    _check_kernel_body_ops(kernel)
    for value in _linear_values(kernel):
        if _is_linear(value):
            _check_single_use(value, f"kernel @{kernel.sym_name.data}")


def _check_callback_declaration(op: SelectorOp | DecoderOp) -> None:
    if op.input_count < 0:
        raise LinearityError(f"callback @{op.sym_name.data} has a negative bit-input count")
    if isinstance(op, DecoderOp) and op.input_count == 0:
        raise LinearityError(f"decoder @{op.sym_name.data} must accept at least one bit")
    if "source" in op.attributes:
        raise LinearityError(
            f"callback @{op.sym_name.data} must encode its source in its symbol"
        )
    try:
        resolve_callback(op.sym_name.data)
    except ValueError as exc:
        raise LinearityError(str(exc)) from exc


def _check_call(op: CallOp, kernels: dict[str, KernelOp]) -> None:
    name = _symbol_name(op.callee)
    kernel = kernels.get(name)
    if kernel is None:
        raise LinearityError(f"qstack.call references unknown kernel @{name}")
    _check_same_types(_type_list(op.arguments), kernel.input_types, f"qstack.call @{name} has wrong argument types")
    _check_same_types(_type_list(op.results), kernel.declared_result_types, f"qstack.call @{name} has wrong result types")


def _check_decode(op: DecodeOp, decoders: dict[str, DecoderOp]) -> None:
    name = _symbol_name(op.callee)
    decoder = decoders.get(name)
    if decoder is None:
        raise LinearityError(f"qstack.decode references unknown decoder @{name}")
    if len(op.bit_operands) != decoder.input_count:
        raise LinearityError(f"qstack.decode @{name} has wrong bit-operand count")


def _check_select(
    op: SelectOp,
    kernels: dict[str, KernelOp],
    selectors: dict[str, SelectorOp],
) -> None:
    selector_name = _symbol_name(op.callee)
    selector = selectors.get(selector_name)
    if selector is None:
        raise LinearityError(f"qstack.select references unknown selector @{selector_name}")
    if len(op.bit_operands) != selector.input_count:
        raise LinearityError(f"qstack.select @{selector_name} has wrong bit-operand count")
    for label, target in op.cases.data.items():
        if not isinstance(target, SymbolRefAttr):
            raise LinearityError(f"qstack.select case {label!r} is not a kernel symbol reference")
        target_name = _symbol_name(target)
        kernel = kernels.get(target_name)
        if kernel is None:
            raise LinearityError(f"qstack.select case {label!r} references unknown kernel @{target_name}")
        _check_same_types(
            _type_list(op.case_arguments),
            kernel.input_types,
            f"qstack.select case {label!r} has incompatible kernel inputs",
        )
        _check_same_types(
            _type_list(op.results),
            kernel.declared_result_types,
            f"qstack.select case {label!r} has incompatible kernel results",
        )


def verify_module(module: ModuleOp) -> None:
    """Validate a closed kernel-only qstack module.

    The verifier is intentionally structural. It establishes the IR invariants
    required by execution but does not compare input and output compiler-pass
    semantics.
    """

    history = module.attributes.get(PASS_HISTORY_ATTR)
    if history is not None and (
        not isinstance(history, ArrayAttr)
        or any(not isinstance(entry, StringAttr) for entry in history)
    ):
        raise LinearityError(
            f"module attribute {PASS_HISTORY_ATTR!r} must be an array of strings"
        )

    top_level = list(module.body.ops)
    allowed = (KernelOp, SelectorOp, DecoderOp)
    for op in top_level:
        if not isinstance(op, allowed):
            raise LinearityError(f"module contains forbidden top-level operation {op.name}")

    symbols: dict[str, Operation] = {}
    for op in top_level:
        name = op.sym_name.data
        if name in symbols:
            raise LinearityError(f"duplicate qstack symbol @{name}")
        symbols[name] = op

    kernels = {name: op for name, op in symbols.items() if isinstance(op, KernelOp)}
    selectors = {name: op for name, op in symbols.items() if isinstance(op, SelectorOp)}
    decoders = {name: op for name, op in symbols.items() if isinstance(op, DecoderOp)}
    main = kernels.get("main")
    if main is None:
        raise LinearityError("module must define exactly one qstack.kernel @main")
    if main.input_types:
        raise LinearityError("qstack.kernel @main must not have borrowed inputs")
    if any(isinstance(typ, QubitType) for typ in main.declared_result_types):
        raise LinearityError("qstack.kernel @main cannot return a qubit")

    for callback in [*selectors.values(), *decoders.values()]:
        _check_callback_declaration(callback)
    for kernel in kernels.values():
        _check_kernel_shape(kernel)
        for op in kernel.body.blocks[0].ops:
            if isinstance(op, CallOp):
                _check_call(op, kernels)
            elif isinstance(op, DecodeOp):
                _check_decode(op, decoders)
            elif isinstance(op, SelectOp):
                _check_select(op, kernels, selectors)


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
