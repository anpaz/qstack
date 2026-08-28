"""Structural verifier for the kernel-only qstack IR.

This module enforces the executable shape from :mod:`docs.DESIGN`; it does
not attempt semantic equivalence checking or callback-obligation generation.
"""

from __future__ import annotations

from collections.abc import Iterable

from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr
from xdsl.ir import Operation, SSAValue

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


class LinearityError(Exception):
    """Raised for any structural or linearity violation in a qstack module."""


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


def _verify_kernel_body_ops(kernel: KernelOp) -> None:
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


def _verify_kernel_shape(kernel: KernelOp) -> None:
    if len(kernel.body.blocks) != 1:
        raise LinearityError(f"kernel @{kernel.sym_name.data} must have exactly one block")
    if kernel.allocation_count < 0:
        raise LinearityError(f"kernel @{kernel.sym_name.data} has a negative allocation count")
    block = kernel.body.blocks[0]
    expected_args = [*kernel.input_types, *[QubitType() for _ in range(kernel.allocation_count)]]
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
    _verify_kernel_body_ops(kernel)
    for value in _linear_values(kernel):
        if _is_linear(value):
            _check_single_use(value, f"kernel @{kernel.sym_name.data}")


def _verify_callback_declaration(op: SelectorOp | DecoderOp) -> None:
    if op.input_count < 0:
        raise LinearityError(f"callback @{op.sym_name.data} has a negative bit-input count")
    if isinstance(op, DecoderOp) and op.input_count == 0:
        raise LinearityError(f"decoder @{op.sym_name.data} must accept at least one bit")


def _verify_call(op: CallOp, kernels: dict[str, KernelOp]) -> None:
    name = _symbol_name(op.callee)
    kernel = kernels.get(name)
    if kernel is None:
        raise LinearityError(f"qstack.call references unknown kernel @{name}")
    _check_same_types(_type_list(op.arguments), kernel.input_types, f"qstack.call @{name} has wrong argument types")
    _check_same_types(_type_list(op.results), kernel.declared_result_types, f"qstack.call @{name} has wrong result types")


def _verify_decode(op: DecodeOp, decoders: dict[str, DecoderOp]) -> None:
    name = _symbol_name(op.callee)
    decoder = decoders.get(name)
    if decoder is None:
        raise LinearityError(f"qstack.decode references unknown decoder @{name}")
    if len(op.bit_operands) != decoder.input_count:
        raise LinearityError(f"qstack.decode @{name} has wrong bit-operand count")


def _verify_select(
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
        _verify_callback_declaration(callback)
    for kernel in kernels.values():
        _verify_kernel_shape(kernel)
        for op in kernel.body.blocks[0].ops:
            if isinstance(op, CallOp):
                _verify_call(op, kernels)
            elif isinstance(op, DecodeOp):
                _verify_decode(op, decoders)
            elif isinstance(op, SelectOp):
                _verify_select(op, kernels, selectors)
