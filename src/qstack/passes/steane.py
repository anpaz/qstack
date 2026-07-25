"""Steane [[7,1,3]] QEC lowering.

Each logical qubit expands to seven physical qubits. Allocated blocks are
prepared as encoded |0>, supported Clifford gates are transversal, syndrome
extraction uses three temporary ancillas, and final physical measurements are
decoded back to one logical bit at function scope.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from xdsl.dialects.builtin import FunctionType, ModuleOp, SymbolRefAttr, UnitAttr
from xdsl.dialects.func import CallOp, FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Attribute, Block, Operation, Region, SSAValue

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, HOp, XOp, ZOp
from qstack.dialect.core import (
    DecodeOp,
    InvokeOp,
    KernelOp,
    MeasureOp,
    ReturnOp,
    SelectOp,
)
from qstack.verifier import verify_module

logger = logging.getLogger("qstack")

_WIDTH = 7
_DECODER = "steane_decode"
_SYNDROME_SELECTOR = "steane_syndrome"
_NO_CORRECTION = "__steane_identity"
_X_CORRECTIONS = tuple(f"__steane_correct_x_{i}" for i in range(_WIDTH))
_Z_CORRECTIONS = tuple(f"__steane_correct_z_{i}" for i in range(_WIDTH))
_STABILIZER_SUPPORTS = (
    (0, 1, 3, 4),
    (0, 2, 3, 5),
    (1, 2, 3, 6),
)
_SYNDROME_TABLE = {
    (0, 0, 0): None,
    (0, 0, 1): 6,
    (0, 1, 0): 5,
    (0, 1, 1): 3,
    (1, 0, 0): 4,
    (1, 0, 1): 2,
    (1, 1, 0): 1,
    (1, 1, 1): 0,
}


class SteaneCompileError(Exception):
    """Raised when a module cannot be lowered to the Steane code."""


def steane_syndrome_label(b0: int, b1: int, b2: int) -> str:
    """Return the correction-menu label for a three-bit syndrome."""

    syndrome = (b0, b1, b2)
    fault = _SYNDROME_TABLE.get(syndrome)
    logger.debug("syndrome: %s, correction: %s", syndrome, fault)
    return "none" if fault is None else str(fault)


def steane_decode_bits(*bits: int) -> int:
    """Correct one physical bit fault and return the logical parity."""

    if len(bits) != _WIDTH:
        raise ValueError(f"Steane decoding expects {_WIDTH} bits, got {len(bits)}")
    corrected = list(bits)
    syndrome = tuple(
        sum(corrected[index] for index in support) % 2
        for support in _STABILIZER_SUPPORTS
    )
    fault = _SYNDROME_TABLE.get(syndrome)
    logger.debug(
        "outcome: %s, syndrome: %s, correction: %s",
        list(bits),
        syndrome,
        fault,
    )
    if fault is not None:
        corrected[fault] ^= 1
    return sum(corrected) % 2


def register_steane_callbacks(registry) -> None:
    """Register the Steane decoder and syndrome selector."""

    registry.decoder(_DECODER)(steane_decode_bits)
    registry.selector(_SYNDROME_SELECTOR)(
        lambda *, b0, b1, b2: steane_syndrome_label(b0, b1, b2)
    )


def _expand_type(typ: Attribute) -> list[Attribute]:
    if isinstance(typ, QubitType):
        return [QubitType() for _ in range(_WIDTH)]
    return [typ]


def _expand_types(types: Iterable[Attribute]) -> list[Attribute]:
    return [expanded for typ in types for expanded in _expand_type(typ)]


def _expand_function_type(function_type: FunctionType) -> FunctionType:
    return FunctionType.from_lists(
        _expand_types(function_type.inputs.data),
        _expand_types(function_type.outputs.data),
    )


def _copy_attributes(source: Operation, destination: Operation) -> None:
    destination.attributes.update(source.attributes)


def _copy_name_hints(source: Sequence[SSAValue], destination: Sequence[SSAValue]) -> None:
    for old, new in zip(source, destination):
        if old.name_hint is not None:
            new.name_hint = old.name_hint


def _prepare_zero(block: Block, qubits: Sequence[SSAValue]) -> tuple[SSAValue, ...]:
    current = list(qubits)
    for index in (4, 5, 6):
        op = HOp(current[index])
        block.add_op(op)
        current[index] = op.result
    for control, target in (
        (4, 0),
        (4, 1),
        (4, 3),
        (5, 0),
        (5, 2),
        (5, 3),
        (6, 1),
        (6, 2),
        (6, 3),
    ):
        op = CxOp(current[control], current[target])
        block.add_op(op)
        current[control] = op.control_out
        current[target] = op.target_out
    return tuple(current)


def _correction_menu(symbols: Sequence[str]) -> dict[str, SymbolRefAttr]:
    return {
        "none": SymbolRefAttr(_NO_CORRECTION),
        **{str(index): SymbolRefAttr(symbol) for index, symbol in enumerate(symbols)},
    }


def _apply_correction(
    block: Block,
    bits: Sequence[SSAValue],
    data: Sequence[SSAValue],
    symbols: Sequence[str],
) -> tuple[SSAValue, ...]:
    function_type = FunctionType.from_lists(
        [QubitType() for _ in range(_WIDTH)],
        [QubitType() for _ in range(_WIDTH)],
    )
    select = SelectOp(
        callee=SymbolRefAttr(_SYNDROME_SELECTOR),
        bit_names=["b0", "b1", "b2"],
        bit_operands=list(bits),
        continuations=_correction_menu(symbols),
        result_type=function_type,
    )
    block.add_op(select)
    invoke = InvokeOp(
        callee=select.result,
        args=list(data),
        result_types=[QubitType() for _ in range(_WIDTH)],
    )
    block.add_op(invoke)
    return tuple(invoke.results)


def _extract_syndrome(
    block: Block,
    data: Sequence[SSAValue],
    *,
    phase_errors: bool,
) -> tuple[SSAValue, ...]:
    body = Block(arg_types=[QubitType(), QubitType(), QubitType()])
    ancillas = list(body.args)
    current = list(data)

    if phase_errors:
        for index in range(3):
            op = HOp(ancillas[index])
            body.add_op(op)
            ancillas[index] = op.result
        for ancilla_index, support in enumerate(_STABILIZER_SUPPORTS):
            for data_index in support:
                op = CxOp(ancillas[ancilla_index], current[data_index])
                body.add_op(op)
                ancillas[ancilla_index] = op.control_out
                current[data_index] = op.target_out
        for index in range(3):
            op = HOp(ancillas[index])
            body.add_op(op)
            ancillas[index] = op.result
        correction_symbols = _Z_CORRECTIONS
    else:
        for ancilla_index, support in enumerate(_STABILIZER_SUPPORTS):
            for data_index in support:
                op = CxOp(current[data_index], ancillas[ancilla_index])
                body.add_op(op)
                current[data_index] = op.control_out
                ancillas[ancilla_index] = op.target_out
        correction_symbols = _X_CORRECTIONS

    measurements = []
    for ancilla in ancillas:
        measure = MeasureOp(operand=ancilla)
        body.add_op(measure)
        measurements.append(measure.result)
    body.add_op(ReturnOp(operands=[*measurements, *current]))

    kernel = KernelOp(
        result_types=[
            BitType(),
            BitType(),
            BitType(),
            *[QubitType() for _ in range(_WIDTH)],
        ],
        region=Region([body]),
    )
    block.add_op(kernel)
    return _apply_correction(
        block,
        kernel.results[:3],
        kernel.results[3:],
        correction_symbols,
    )


def _error_correct(block: Block, data: Sequence[SSAValue]) -> tuple[SSAValue, ...]:
    current = _extract_syndrome(block, data, phase_errors=False)
    return _extract_syndrome(block, current, phase_errors=True)


class _FunctionRewriter:
    def __init__(self, function_types: dict[str, FunctionType]):
        self.function_types = function_types
        self.values: dict[SSAValue, tuple[SSAValue, ...]] = {}
        self.inserted_decoder = False
        self.inserted_correction = False
        self.kernel_depth = 0
        self.handlers = {
            HOp: self._rewrite_single_qubit_gate,
            XOp: self._rewrite_single_qubit_gate,
            ZOp: self._rewrite_single_qubit_gate,
            CxOp: self._rewrite_two_qubit_gate,
            MeasureOp: self._rewrite_measure,
            KernelOp: self._rewrite_kernel,
            DecodeOp: self._rewrite_decode,
            SelectOp: self._rewrite_select,
            InvokeOp: self._rewrite_invoke,
            CallOp: self._rewrite_call,
            ReturnOp: self._rewrite_kernel_return,
            FuncReturn: self._rewrite_func_return,
        }

    def rewrite(self, fn: FuncOp) -> FuncOp:
        new_type = self.function_types[fn.sym_name.data]
        new_entry = Block(arg_types=list(new_type.inputs.data))
        self._map_block_args(fn.body.block.args, new_entry.args)
        self._rewrite_block(fn.body.block, new_entry)
        new_fn = FuncOp(
            fn.sym_name.data,
            new_type,
            Region([new_entry]),
            visibility=fn.properties.get("sym_visibility"),
            arg_attrs=fn.properties.get("arg_attrs"),
            res_attrs=fn.properties.get("res_attrs"),
        )
        _copy_attributes(fn, new_fn)
        return new_fn

    def _map_block_args(
        self,
        old_args: Sequence[SSAValue],
        new_args: Sequence[SSAValue],
    ) -> None:
        cursor = 0
        for old_arg in old_args:
            width = _WIDTH if isinstance(old_arg.type, QubitType) else 1
            mapped = tuple(new_args[cursor : cursor + width])
            cursor += width
            self.values[old_arg] = mapped
            _copy_name_hints([old_arg] * width, mapped)

    def _mapped(self, value: SSAValue) -> tuple[SSAValue, ...]:
        try:
            return self.values[value]
        except KeyError as exc:
            raise SteaneCompileError(
                f"steane: no rewritten value for {value!r}"
            ) from exc

    def _single(self, value: SSAValue) -> SSAValue:
        mapped = self._mapped(value)
        if len(mapped) != 1:
            raise SteaneCompileError(
                f"steane: expected one rewritten value for {value!r}, "
                f"got {len(mapped)}"
            )
        return mapped[0]

    def _flatten(self, values: Iterable[SSAValue]) -> list[SSAValue]:
        return [new_value for old_value in values for new_value in self._mapped(old_value)]

    def _rewrite_block(self, source: Block, destination: Block) -> None:
        for op in source.ops:
            self._rewrite_op(op, destination)

    def _rewrite_op(self, op: Operation, destination: Block) -> None:
        handler = self.handlers.get(type(op))
        if handler is None:
            raise SteaneCompileError(f"steane: unsupported operation {op.name!r}")
        handler(op, destination)

    def _rewrite_kernel_return(self, op: ReturnOp, destination: Block) -> None:
        destination.add_op(ReturnOp(operands=self._flatten(op.operands)))

    def _rewrite_func_return(self, op: FuncReturn, destination: Block) -> None:
        destination.add_op(FuncReturn.create(operands=self._flatten(op.operands)))

    def _rewrite_single_qubit_gate(self, op: Operation, destination: Block) -> None:
        rewritten = []
        for qubit in self._mapped(op.operands[0]):
            new_op = type(op)(qubit)
            _copy_attributes(op, new_op)
            destination.add_op(new_op)
            rewritten.append(new_op.results[0])
        corrected = _error_correct(destination, rewritten)
        self.inserted_correction = True
        self.values[op.results[0]] = corrected
        _copy_name_hints([op.results[0]] * _WIDTH, corrected)

    def _rewrite_two_qubit_gate(self, op: CxOp, destination: Block) -> None:
        controls = self._mapped(op.control)
        targets = self._mapped(op.target)
        control_results = []
        target_results = []
        for control, target in zip(controls, targets, strict=True):
            new_op = CxOp(control, target)
            destination.add_op(new_op)
            control_results.append(new_op.control_out)
            target_results.append(new_op.target_out)
        corrected_controls = _error_correct(destination, control_results)
        corrected_targets = _error_correct(destination, target_results)
        self.inserted_correction = True
        self.values[op.control_out] = corrected_controls
        self.values[op.target_out] = corrected_targets

    def _rewrite_measure(self, op: MeasureOp, destination: Block) -> None:
        measured = []
        for qubit in self._mapped(op.qubit):
            new_op = MeasureOp(operand=qubit)
            destination.add_op(new_op)
            measured.append(new_op.result)
        self.values[op.result] = tuple(measured)

    def _rewrite_kernel(self, op: KernelOp, destination: Block) -> None:
        if self.kernel_depth and any(isinstance(result.type, BitType) for result in op.results):
            raise SteaneCompileError(
                "steane: source allocating kernels nested inside another kernel "
                "are not yet supported"
            )

        source_entry = op.body.block
        new_entry = Block(
            arg_types=_expand_types(arg.type for arg in source_entry.args)
        )
        self._map_block_args(source_entry.args, new_entry.args)
        for source_arg in source_entry.args:
            prepared = _prepare_zero(new_entry, self._mapped(source_arg))
            self.values[source_arg] = _error_correct(new_entry, prepared)
            self.inserted_correction = True

        self.kernel_depth += 1
        try:
            self._rewrite_block(source_entry, new_entry)
        finally:
            self.kernel_depth -= 1

        result_types = [
            expanded
            for result in op.results
            for expanded in (
                [BitType() for _ in range(_WIDTH)]
                if isinstance(result.type, BitType)
                else _expand_type(result.type)
            )
        ]
        new_kernel = KernelOp(result_types=result_types, region=Region([new_entry]))
        _copy_attributes(op, new_kernel)
        destination.add_op(new_kernel)

        cursor = 0
        for old_result in op.results:
            if isinstance(old_result.type, QubitType):
                mapped = tuple(new_kernel.results[cursor : cursor + _WIDTH])
                cursor += _WIDTH
                self.values[old_result] = mapped
            elif isinstance(old_result.type, BitType):
                physical_bits = list(
                    new_kernel.results[cursor : cursor + _WIDTH]
                )
                cursor += _WIDTH
                decode = DecodeOp(
                    callee=SymbolRefAttr(_DECODER),
                    bit_operands=physical_bits,
                )
                destination.add_op(decode)
                self.values[old_result] = (decode.result,)
                self.inserted_decoder = True
            else:
                raise SteaneCompileError(
                    f"steane: unsupported kernel result type {old_result.type}"
                )

    def _rewrite_decode(self, op: DecodeOp, destination: Block) -> None:
        new_op = DecodeOp(
            callee=op.callee,
            bit_operands=[self._single(bit) for bit in op.bit_operands],
        )
        _copy_attributes(op, new_op)
        destination.add_op(new_op)
        self.values[op.result] = (new_op.result,)

    def _rewrite_select(self, op: SelectOp, destination: Block) -> None:
        new_op = SelectOp(
            callee=op.callee,
            bit_names=[name.data for name in op.bit_names.data],
            bit_operands=[self._single(bit) for bit in op.bit_operands],
            continuations=dict(op.continuations.data),
            result_type=_expand_function_type(op.result.type),
        )
        _copy_attributes(op, new_op)
        destination.add_op(new_op)
        self.values[op.result] = (new_op.result,)

    def _rewrite_invoke(self, op: InvokeOp, destination: Block) -> None:
        new_op = InvokeOp(
            callee=self._single(op.callee),
            args=self._flatten(op.args),
            result_types=_expand_types(result.type for result in op.results),
        )
        _copy_attributes(op, new_op)
        destination.add_op(new_op)
        self._map_results(op.results, new_op.results)

    def _rewrite_call(self, op: CallOp, destination: Block) -> None:
        callee = op.callee.root_reference.data
        try:
            result_types = self.function_types[callee].outputs.data
        except KeyError as exc:
            raise SteaneCompileError(
                f"steane: func.call references unknown symbol @{callee}"
            ) from exc
        new_op = CallOp(op.callee, self._flatten(op.arguments), list(result_types))
        _copy_attributes(op, new_op)
        destination.add_op(new_op)
        self._map_results(op.results, new_op.results)

    def _map_results(
        self,
        old_results: Sequence[SSAValue],
        new_results: Sequence[SSAValue],
    ) -> None:
        cursor = 0
        for old_result in old_results:
            width = _WIDTH if isinstance(old_result.type, QubitType) else 1
            mapped = tuple(new_results[cursor : cursor + width])
            cursor += width
            self.values[old_result] = mapped


def _is_callback_declaration(fn: FuncOp) -> bool:
    return fn.is_declaration and (
        "qstack.selector" in fn.attributes or "qstack.decoder" in fn.attributes
    )


def _clone_declaration(fn: FuncOp, function_type: FunctionType) -> FuncOp:
    cloned = FuncOp(
        fn.sym_name.data,
        function_type,
        Region(),
        visibility=fn.properties.get("sym_visibility"),
        arg_attrs=fn.properties.get("arg_attrs"),
        res_attrs=fn.properties.get("res_attrs"),
    )
    _copy_attributes(fn, cloned)
    return cloned


def _decoder_declaration() -> FuncOp:
    declaration = FuncOp.external(
        _DECODER,
        [BitType() for _ in range(_WIDTH)],
        [BitType()],
    )
    declaration.attributes["qstack.decoder"] = UnitAttr()
    return declaration


def _selector_declaration() -> FuncOp:
    declaration = FuncOp.external(
        _SYNDROME_SELECTOR,
        [BitType(), BitType(), BitType()],
        [],
    )
    declaration.attributes["qstack.selector"] = UnitAttr()
    return declaration


def _correction_function(name: str, gate_type=None, index: int | None = None) -> FuncOp:
    body = Block(arg_types=[QubitType() for _ in range(_WIDTH)])
    outputs = list(body.args)
    if gate_type is not None and index is not None:
        gate = gate_type(outputs[index])
        body.add_op(gate)
        outputs[index] = gate.result
    body.add_op(FuncReturn.create(operands=outputs))
    return FuncOp(
        name,
        FunctionType.from_lists(
            [QubitType() for _ in range(_WIDTH)],
            [QubitType() for _ in range(_WIDTH)],
        ),
        Region([body]),
        visibility="private",
    )


def _correction_support_functions() -> list[FuncOp]:
    return [
        _selector_declaration(),
        _correction_function(_NO_CORRECTION),
        *[
            _correction_function(name, XOp, index)
            for index, name in enumerate(_X_CORRECTIONS)
        ],
        *[
            _correction_function(name, ZOp, index)
            for index, name in enumerate(_Z_CORRECTIONS)
        ],
    ]


def compile_steane(module: ModuleOp) -> ModuleOp:
    """Return a Steane-encoded copy of ``module``."""

    functions: dict[str, FuncOp] = {}
    for op in module.body.ops:
        if not isinstance(op, FuncOp):
            raise SteaneCompileError(
                f"steane: unsupported top-level operation {op.name!r}"
            )
        name = op.sym_name.data
        if name in functions:
            raise SteaneCompileError(f"steane: duplicate function symbol @{name}")
        functions[name] = op

    reserved = {
        _DECODER,
        _SYNDROME_SELECTOR,
        _NO_CORRECTION,
        *_X_CORRECTIONS,
        *_Z_CORRECTIONS,
    }
    collisions = reserved.intersection(functions)
    if collisions:
        names = ", ".join(f"@{name}" for name in sorted(collisions))
        raise SteaneCompileError(
            f"steane: module already defines reserved support symbols: {names}"
        )

    function_types = {
        name: (
            fn.function_type
            if _is_callback_declaration(fn)
            else _expand_function_type(fn.function_type)
        )
        for name, fn in functions.items()
    }

    rewritten: list[Operation] = []
    inserted_decoder = False
    inserted_correction = False
    for fn in functions.values():
        if fn.is_declaration:
            rewritten.append(_clone_declaration(fn, function_types[fn.sym_name.data]))
            continue
        rewriter = _FunctionRewriter(function_types)
        rewritten.append(rewriter.rewrite(fn))
        inserted_decoder = inserted_decoder or rewriter.inserted_decoder
        inserted_correction = inserted_correction or rewriter.inserted_correction

    if inserted_decoder:
        rewritten.append(_decoder_declaration())
    if inserted_correction:
        rewritten.extend(_correction_support_functions())

    output = ModuleOp(
        rewritten,
        attributes=dict(module.attributes),
        sym_name=module.properties.get("sym_name"),
    )
    output.verify()
    verify_module(output)
    return output
