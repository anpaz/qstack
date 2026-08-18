"""Phase-flip repetition-3 lowering.

The pass is a pure module-to-module transformation. Every logical qubit is
expanded to three physical qubits. Freshly allocated logical |0> states are
prepared as phase-code |0_L> = |+++>, supported Clifford gates are lowered in
the phase-code basis, and every logical measurement is measured in the X basis
before being decoded at function scope with ``qstack.decode
@phase_majority_vote``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from xdsl.dialects.builtin import FunctionType, ModuleOp, SymbolRefAttr, UnitAttr
from xdsl.dialects.func import CallOp, FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Attribute, Block, Operation, Region, SSAValue

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, YOp, ZOp
from qstack.dialect.core import DecodeOp, InvokeOp, KernelOp, MeasureOp, ReturnOp, SelectOp
from qstack.verifier import verify_module

_PHASE_MAJORITY_VOTE = "phase_majority_vote"
_WIDTH = 3
_UNSUPPORTED_GATES = (YOp, ZOp, SOp, CzOp)


class Rep3PhaseCompileError(Exception):
    """Raised when a module cannot be lowered by the phase repetition-code pass."""


def register_rep3_phase_callbacks(registry) -> None:
    """Register the phase repetition-code decoder on a callback registry."""

    @registry.decoder(_PHASE_MAJORITY_VOTE)
    def _phase_majority_vote(b0: int, b1: int, b2: int) -> int:
        return 1 if (b0 + b1 + b2) >= 2 else 0


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
            width = _WIDTH if isinstance(old_arg.type, QubitType) else 1
            expanded = tuple(new_args[cursor : cursor + width])
            self.values[old_arg] = expanded
            _copy_name_hints([old_arg] * width, expanded)
            cursor += width

    def _mapped(self, value: SSAValue) -> tuple[SSAValue, ...]:
        try:
            return self.values[value]
        except KeyError as exc:
            raise Rep3PhaseCompileError(
                f"rep3-phase: no rewritten value for {value!r}"
            ) from exc

    def _single(self, value: SSAValue) -> SSAValue:
        mapped = self._mapped(value)
        if len(mapped) != 1:
            raise Rep3PhaseCompileError(
                f"rep3-phase: expected one rewritten value for {value!r}, got {len(mapped)}"
            )
        return mapped[0]

    def _flatten(self, values: Iterable[SSAValue]) -> list[SSAValue]:
        return [new_value for old_value in values for new_value in self._mapped(old_value)]

    def _rewrite_block(self, source: Block, destination: Block) -> None:
        for op in source.ops:
            self._rewrite_op(op, destination)

    def _rewrite_op(self, op: Operation, destination: Block) -> None:
        if isinstance(op, XOp):
            self._rewrite_logical_x(op, destination)
        elif isinstance(op, HOp):
            self._rewrite_logical_h(op, destination)
        elif isinstance(op, CxOp):
            self._rewrite_logical_cx(op, destination)
        elif isinstance(op, _UNSUPPORTED_GATES):
            raise Rep3PhaseCompileError(
                f"rep3-phase: unsupported Clifford operation {op.name!r}"
            )
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
            raise Rep3PhaseCompileError(f"rep3-phase: unsupported operation {op.name!r}")

    def _prepare_allocated_zero(self, value: SSAValue, destination: Block) -> None:
        prepared = []
        for qubit in self._mapped(value):
            h = HOp(qubit)
            destination.add_op(h)
            prepared.append(h.result)
        self.values[value] = tuple(prepared)
        _copy_name_hints([value] * _WIDTH, prepared)

    def _rewrite_logical_x(self, op: XOp, destination: Block) -> None:
        rewritten = []
        for qubit in self._mapped(op.qubit):
            z = ZOp(qubit)
            _copy_attributes(op, z)
            destination.add_op(z)
            rewritten.append(z.result)
        self.values[op.result] = tuple(rewritten)
        _copy_name_hints([op.result] * _WIDTH, rewritten)

    def _rewrite_logical_h(self, op: HOp, destination: Block) -> None:
        q0, q1, q2 = self._mapped(op.qubit)

        h0 = HOp(q0)
        _copy_attributes(op, h0)
        destination.add_op(h0)

        cz01 = CzOp(h0.result, q1)
        _copy_attributes(op, cz01)
        destination.add_op(cz01)

        cz02 = CzOp(cz01.control_out, q2)
        _copy_attributes(op, cz02)
        destination.add_op(cz02)

        mapped = (cz02.target_out, cz01.target_out, cz02.control_out)
        self.values[op.result] = mapped
        _copy_name_hints([op.result] * _WIDTH, mapped)

    def _rewrite_logical_cx(self, op: CxOp, destination: Block) -> None:
        controls = self._mapped(op.control)
        targets = self._mapped(op.target)
        control_results = []
        target_results = []
        for control, target in zip(controls, targets, strict=True):
            cx = CxOp(control, target)
            _copy_attributes(op, cx)
            destination.add_op(cx)
            control_results.append(cx.control_out)
            target_results.append(cx.target_out)
        self.values[op.control_out] = tuple(control_results)
        self.values[op.target_out] = tuple(target_results)
        _copy_name_hints([op.control_out] * _WIDTH, control_results)
        _copy_name_hints([op.target_out] * _WIDTH, target_results)

    def _rewrite_measure(self, op: MeasureOp, destination: Block) -> None:
        measured = []
        for qubit in self._mapped(op.qubit):
            basis_change = HOp(qubit)
            _copy_attributes(op, basis_change)
            destination.add_op(basis_change)
            measure = MeasureOp(operand=basis_change.result)
            _copy_attributes(op, measure)
            destination.add_op(measure)
            measured.append(measure.result)
        self.values[op.result] = tuple(measured)
        _copy_name_hints([op.result] * _WIDTH, measured)

    def _rewrite_kernel(self, op: KernelOp, destination: Block) -> None:
        if self.kernel_depth and any(isinstance(result.type, BitType) for result in op.results):
            raise Rep3PhaseCompileError(
                "rep3-phase: allocating kernels nested inside another kernel require "
                "kernel restructuring to keep decoders at function scope"
            )

        source_entry = op.body.block
        new_entry = Block(arg_types=_expand_types(arg.type for arg in source_entry.args))
        self._map_block_args(source_entry.args, new_entry.args)
        for arg in source_entry.args:
            if isinstance(arg.type, QubitType):
                self._prepare_allocated_zero(arg, new_entry)
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
                _copy_name_hints([old_result] * _WIDTH, mapped)
                continue
            if isinstance(old_result.type, BitType):
                physical_bits = list(new_kernel.results[cursor : cursor + _WIDTH])
                cursor += _WIDTH
                decode = DecodeOp(
                    callee=SymbolRefAttr(_PHASE_MAJORITY_VOTE),
                    bit_operands=physical_bits,
                )
                destination.add_op(decode)
                self.values[old_result] = (decode.result,)
                self.inserted_decoder = True
                if old_result.name_hint is not None:
                    decode.result.name_hint = old_result.name_hint
                continue
            raise Rep3PhaseCompileError(
                f"rep3-phase: unsupported kernel result type {old_result.type}"
            )

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
            raise Rep3PhaseCompileError(
                f"rep3-phase: func.call references unknown symbol @{callee}"
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


def _phase_majority_vote_declaration() -> FuncOp:
    declaration = FuncOp.external(
        _PHASE_MAJORITY_VOTE,
        [BitType(), BitType(), BitType()],
        [BitType()],
    )
    declaration.attributes["qstack.decoder"] = UnitAttr()
    return declaration


def _validate_existing_phase_majority_vote(fn: FuncOp) -> None:
    expected = FunctionType.from_lists(
        [BitType(), BitType(), BitType()],
        [BitType()],
    )
    if (
        not fn.is_declaration
        or "qstack.decoder" not in fn.attributes
        or fn.function_type != expected
    ):
        raise Rep3PhaseCompileError(
            "@phase_majority_vote already exists but is not a decoder declaration "
            "with signature (!qstack.bit, !qstack.bit, !qstack.bit) -> !qstack.bit"
        )


def compile_rep3_phase(module: ModuleOp) -> ModuleOp:
    """Return a phase-repetition-3 encoded copy of ``module``."""

    functions: dict[str, FuncOp] = {}
    for op in module.body.ops:
        if not isinstance(op, FuncOp):
            raise Rep3PhaseCompileError(
                f"rep3-phase: unsupported top-level operation {op.name!r}"
            )
        name = op.sym_name.data
        if name in functions:
            raise Rep3PhaseCompileError(f"rep3-phase: duplicate function symbol @{name}")
        functions[name] = op

    existing_majority = functions.get(_PHASE_MAJORITY_VOTE)
    if existing_majority is not None:
        _validate_existing_phase_majority_vote(existing_majority)

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
        rewritten_ops.append(_phase_majority_vote_declaration())

    output = ModuleOp(
        rewritten_ops,
        attributes=dict(module.attributes),
        sym_name=module.properties.get("sym_name"),
    )
    output.verify()
    verify_module(output)
    return output
