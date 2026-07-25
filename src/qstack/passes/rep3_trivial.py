"""Three-bit repetition-code lowering.

The pass is a pure module-to-module transformation. Every logical qubit is
expanded to three physical qubits, Clifford gates are applied transversally,
and every logical measurement is expanded to three physical measurements.
The physical bits leave their kernel and are decoded at function scope with
``qstack.decode @majority_vote``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from xdsl.dialects.builtin import FunctionType, ModuleOp, SymbolRefAttr, UnitAttr
from xdsl.dialects.func import CallOp, FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Attribute, Block, Operation, Region, SSAValue

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, ZOp
from qstack.dialect.core import DecodeOp, InvokeOp, KernelOp, MeasureOp, ReturnOp, SelectOp
from qstack.verifier import verify_module

_MAJORITY_VOTE = "majority_vote"
_SINGLE_QUBIT_GATES = (HOp, XOp, ZOp, SOp)
_TWO_QUBIT_GATES = (CxOp, CzOp)


class Rep3CompileError(Exception):
    """Raised when a module cannot be lowered by the repetition-code pass."""


def register_rep3_callbacks(registry) -> None:
    """Register the repetition-code decoder on a callback registry."""

    @registry.decoder(_MAJORITY_VOTE)
    def _majority_vote(b0: int, b1: int, b2: int) -> int:
        return 1 if (b0 + b1 + b2) >= 2 else 0


def _expand_type(typ: Attribute) -> list[Attribute]:
    if isinstance(typ, QubitType):
        return [QubitType(), QubitType(), QubitType()]
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


class _FunctionRewriter:
    """Rewrite one function body using an old-SSA to expanded-SSA map."""

    def __init__(self, function_types: dict[str, FunctionType]):
        self.function_types = function_types
        self.values: dict[SSAValue, tuple[SSAValue, ...]] = {}
        self.inserted_decoder = False
        self.kernel_depth = 0

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
            width = 3 if isinstance(old_arg.type, QubitType) else 1
            expanded = tuple(new_args[cursor : cursor + width])
            self.values[old_arg] = expanded
            _copy_name_hints([old_arg] * width, expanded)
            cursor += width

    def _mapped(self, value: SSAValue) -> tuple[SSAValue, ...]:
        try:
            return self.values[value]
        except KeyError as exc:
            raise Rep3CompileError(f"rep3: no rewritten value for {value!r}") from exc

    def _single(self, value: SSAValue) -> SSAValue:
        mapped = self._mapped(value)
        if len(mapped) != 1:
            raise Rep3CompileError(
                f"rep3: expected one rewritten value for {value!r}, got {len(mapped)}"
            )
        return mapped[0]

    def _flatten(self, values: Iterable[SSAValue]) -> list[SSAValue]:
        return [new_value for old_value in values for new_value in self._mapped(old_value)]

    def _rewrite_block(self, source: Block, destination: Block) -> None:
        for op in source.ops:
            self._rewrite_op(op, destination)

    def _rewrite_op(self, op: Operation, destination: Block) -> None:
        if isinstance(op, _SINGLE_QUBIT_GATES):
            self._rewrite_single_qubit_gate(op, destination)
        elif isinstance(op, _TWO_QUBIT_GATES):
            self._rewrite_two_qubit_gate(op, destination)
        elif isinstance(op, MeasureOp):
            self._rewrite_measure(op, destination)
        elif isinstance(op, KernelOp):
            self._rewrite_kernel(op, destination)
        elif isinstance(op, DecodeOp):
            self._rewrite_decode(op, destination)
        elif isinstance(op, SelectOp):
            self._rewrite_select(op, destination)
        elif isinstance(op, InvokeOp):
            self._rewrite_invoke(op, destination)
        elif isinstance(op, CallOp):
            self._rewrite_call(op, destination)
        elif isinstance(op, ReturnOp):
            new_op = ReturnOp(operands=self._flatten(op.operands))
            _copy_attributes(op, new_op)
            destination.add_op(new_op)
        elif isinstance(op, FuncReturn):
            new_op = FuncReturn.create(operands=self._flatten(op.operands))
            _copy_attributes(op, new_op)
            destination.add_op(new_op)
        else:
            raise Rep3CompileError(f"rep3: unsupported operation {op.name!r}")

    def _rewrite_single_qubit_gate(self, op: Operation, destination: Block) -> None:
        rewritten = []
        for qubit in self._mapped(op.operands[0]):
            new_op = type(op)(qubit)
            _copy_attributes(op, new_op)
            destination.add_op(new_op)
            rewritten.append(new_op.results[0])
        self.values[op.results[0]] = tuple(rewritten)
        _copy_name_hints([op.results[0]] * 3, rewritten)

    def _rewrite_two_qubit_gate(self, op: Operation, destination: Block) -> None:
        controls = self._mapped(op.operands[0])
        targets = self._mapped(op.operands[1])
        control_results = []
        target_results = []
        for control, target in zip(controls, targets, strict=True):
            new_op = type(op)(control, target)
            _copy_attributes(op, new_op)
            destination.add_op(new_op)
            control_results.append(new_op.results[0])
            target_results.append(new_op.results[1])
        self.values[op.results[0]] = tuple(control_results)
        self.values[op.results[1]] = tuple(target_results)
        _copy_name_hints([op.results[0]] * 3, control_results)
        _copy_name_hints([op.results[1]] * 3, target_results)

    def _rewrite_measure(self, op: MeasureOp, destination: Block) -> None:
        measured = []
        for qubit in self._mapped(op.qubit):
            new_op = MeasureOp(operand=qubit)
            _copy_attributes(op, new_op)
            destination.add_op(new_op)
            measured.append(new_op.result)
        self.values[op.result] = tuple(measured)
        _copy_name_hints([op.result] * 3, measured)

    def _rewrite_kernel(self, op: KernelOp, destination: Block) -> None:
        if self.kernel_depth and any(isinstance(result.type, BitType) for result in op.results):
            raise Rep3CompileError(
                "rep3: allocating kernels nested inside another kernel require "
                "kernel restructuring to keep decoders at function scope"
            )

        source_entry = op.body.block
        new_entry = Block(arg_types=_expand_types(arg.type for arg in source_entry.args))
        self._map_block_args(source_entry.args, new_entry.args)
        self.kernel_depth += 1
        try:
            self._rewrite_block(source_entry, new_entry)
        finally:
            self.kernel_depth -= 1

        result_types = [
            expanded
            for result in op.results
            for expanded in (
                [BitType(), BitType(), BitType()]
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
                mapped = tuple(new_kernel.results[cursor : cursor + 3])
                cursor += 3
                self.values[old_result] = mapped
                _copy_name_hints([old_result] * 3, mapped)
                continue
            if isinstance(old_result.type, BitType):
                physical_bits = list(new_kernel.results[cursor : cursor + 3])
                cursor += 3
                decode = DecodeOp(
                    callee=SymbolRefAttr(_MAJORITY_VOTE),
                    bit_operands=physical_bits,
                )
                destination.add_op(decode)
                self.values[old_result] = (decode.result,)
                self.inserted_decoder = True
                if old_result.name_hint is not None:
                    decode.result.name_hint = old_result.name_hint
                continue
            raise Rep3CompileError(f"rep3: unsupported kernel result type {old_result.type}")

    def _rewrite_decode(self, op: DecodeOp, destination: Block) -> None:
        new_op = DecodeOp(
            callee=op.callee,
            bit_operands=[self._single(bit) for bit in op.bit_operands],
        )
        _copy_attributes(op, new_op)
        destination.add_op(new_op)
        self.values[op.result] = (new_op.result,)
        _copy_name_hints(op.results, new_op.results)

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
        _copy_name_hints(op.results, new_op.results)

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
            raise Rep3CompileError(f"rep3: func.call references unknown symbol @{callee}") from exc
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
            width = 3 if isinstance(old_result.type, QubitType) else 1
            mapped = tuple(new_results[cursor : cursor + width])
            cursor += width
            self.values[old_result] = mapped
            _copy_name_hints([old_result] * width, mapped)


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


def _majority_vote_declaration() -> FuncOp:
    declaration = FuncOp.external(
        _MAJORITY_VOTE,
        [BitType(), BitType(), BitType()],
        [BitType()],
    )
    declaration.attributes["qstack.decoder"] = UnitAttr()
    return declaration


def _validate_existing_majority_vote(fn: FuncOp) -> None:
    expected = FunctionType.from_lists(
        [BitType(), BitType(), BitType()],
        [BitType()],
    )
    if (
        not fn.is_declaration
        or "qstack.decoder" not in fn.attributes
        or fn.function_type != expected
    ):
        raise Rep3CompileError(
            "@majority_vote already exists but is not a decoder declaration "
            "with signature (!qstack.bit, !qstack.bit, !qstack.bit) -> !qstack.bit"
        )


def compile_rep3(module: ModuleOp) -> ModuleOp:
    """Return a repetition-3 encoded copy of ``module``."""

    functions: dict[str, FuncOp] = {}
    for op in module.body.ops:
        if not isinstance(op, FuncOp):
            raise Rep3CompileError(f"rep3: unsupported top-level operation {op.name!r}")
        name = op.sym_name.data
        if name in functions:
            raise Rep3CompileError(f"rep3: duplicate function symbol @{name}")
        functions[name] = op

    existing_majority = functions.get(_MAJORITY_VOTE)
    if existing_majority is not None:
        _validate_existing_majority_vote(existing_majority)

    function_types = {
        name: (
            fn.function_type
            if _is_callback_declaration(fn)
            else _expand_function_type(fn.function_type)
        )
        for name, fn in functions.items()
    }

    rewritten_ops: list[Operation] = []
    inserted_decoder = False
    for fn in functions.values():
        if fn.is_declaration:
            rewritten_ops.append(_clone_declaration(fn, function_types[fn.sym_name.data]))
            continue
        rewriter = _FunctionRewriter(function_types)
        rewritten_ops.append(rewriter.rewrite(fn))
        inserted_decoder = inserted_decoder or rewriter.inserted_decoder

    if inserted_decoder and existing_majority is None:
        rewritten_ops.append(_majority_vote_declaration())

    output = ModuleOp(
        rewritten_ops,
        attributes=dict(module.attributes),
        sym_name=module.properties.get("sym_name"),
    )
    output.verify()
    verify_module(output)
    return output
