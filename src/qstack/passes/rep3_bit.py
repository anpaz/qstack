"""Kernel-only three-bit repetition-code lowering."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr
from xdsl.ir import Attribute, Block, Operation, Region, SSAValue

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, ZOp
from qstack.dialect.core import CallOp, DecodeOp, DecoderOp, KernelOp, MeasureOp, ReturnOp, SelectOp, SelectorOp
from qstack.verifier import verify_module

_WIDTH = 3
_DECODER = "__qstack_rep3_bit_decode"
_ONE_QUBIT_GATES = (HOp, XOp, ZOp, SOp)
_TWO_QUBIT_GATES = (CxOp, CzOp)


class Rep3BitCompileError(Exception):
    """Raised when a module contains an operation outside the Rep3 fragment."""


def _expand_type(typ: Attribute) -> list[Attribute]:
    return [QubitType() for _ in range(_WIDTH)] if isinstance(typ, QubitType) else [typ]


def _expand_types(types: Iterable[Attribute]) -> list[Attribute]:
    return [expanded for typ in types for expanded in _expand_type(typ)]


def _has_canonical_decoder(module: ModuleOp) -> bool:
    """Return whether ``module`` already declares this code's decoder."""
    for op in module.body.ops:
        if not hasattr(op, "sym_name") or op.sym_name.data != _DECODER:
            continue
        if isinstance(op, DecoderOp) and op.input_count == _WIDTH:
            return True
        raise Rep3BitCompileError(f"reserved callback symbol @{_DECODER} has an incompatible declaration")
    return False


def _majority_vote(bits: tuple[int, ...]) -> int:
    return 1 if sum(bits) >= 2 else 0


def register_rep3_bit_callbacks(registry) -> None:
    """Install the canonical three-bit majority decoder."""
    if not registry.has_decoder(_DECODER):
        registry.decoder(_DECODER)(_majority_vote)


class _KernelRewriter:
    def __init__(self, signatures: dict[str, tuple[list[Attribute], list[Attribute]]], decoder: str):
        self.signatures = signatures
        self.decoder = decoder
        self.values: dict[SSAValue, tuple[SSAValue, ...]] = {}

    def rewrite(self, source: KernelOp) -> KernelOp:
        inputs, results = self.signatures[source.sym_name.data]
        block = Block(arg_types=[*inputs, *[QubitType() for _ in range(source.allocation_count * _WIDTH)]])
        self._map_values(source.body.block.args, block.args)
        for op in source.body.block.ops:
            self._rewrite_op(op, block)
        return KernelOp(
            source.sym_name.data,
            input_types=inputs,
            result_types=results,
            allocates=source.allocation_count * _WIDTH,
            region=Region([block]),
        )

    def _map_values(self, old: Sequence[SSAValue], new: Sequence[SSAValue]) -> None:
        cursor = 0
        for value in old:
            width = _WIDTH if isinstance(value.type, QubitType) else 1
            mapped = tuple(new[cursor : cursor + width])
            self.values[value] = mapped
            cursor += width

    def _mapped(self, value: SSAValue) -> tuple[SSAValue, ...]:
        try:
            return self.values[value]
        except KeyError as exc:
            raise Rep3BitCompileError(f"no rewritten value for {value!r}") from exc

    def _single(self, value: SSAValue) -> SSAValue:
        mapped = self._mapped(value)
        if len(mapped) != 1:
            raise Rep3BitCompileError(f"expected one bit value for {value!r}")
        return mapped[0]

    def _flatten(self, values: Iterable[SSAValue]) -> list[SSAValue]:
        return [new for value in values for new in self._mapped(value)]

    def _map_results(self, old: Sequence[SSAValue], new: Sequence[SSAValue]) -> None:
        self._map_values(old, new)

    def _rewrite_op(self, op: Operation, block: Block) -> None:
        if isinstance(op, _ONE_QUBIT_GATES):
            results: list[SSAValue] = []
            for qubit in self._mapped(op.operands[0]):
                gate = type(op).create(operands=[qubit], result_types=[QubitType()], properties=dict(op.properties))
                block.add_op(gate)
                results.append(gate.results[0])
            self.values[op.results[0]] = tuple(results)
            return
        if isinstance(op, _TWO_QUBIT_GATES):
            first: list[SSAValue] = []
            second: list[SSAValue] = []
            for control, target in zip(self._mapped(op.operands[0]), self._mapped(op.operands[1]), strict=True):
                gate = type(op).create(
                    operands=[control, target], result_types=[QubitType(), QubitType()], properties=dict(op.properties)
                )
                block.add_op(gate)
                first.append(gate.results[0])
                second.append(gate.results[1])
            self.values[op.results[0]] = tuple(first)
            self.values[op.results[1]] = tuple(second)
            return
        if isinstance(op, MeasureOp):
            physical_bits: list[SSAValue] = []
            for qubit in self._mapped(op.qubit):
                measure = MeasureOp(operand=qubit)
                block.add_op(measure)
                physical_bits.append(measure.result)
            decode = DecodeOp(callee=self.decoder, bit_operands=physical_bits)
            block.add_op(decode)
            self.values[op.result] = (decode.result,)
            return
        if isinstance(op, CallOp):
            _, result_types = self.signatures[op.callee.root_reference.data]
            call = CallOp(op.callee, self._flatten(op.arguments), result_types)
            block.add_op(call)
            self._map_results(op.results, call.results)
            return
        if isinstance(op, DecodeOp):
            decode = DecodeOp(callee=op.callee, bit_operands=[self._single(bit) for bit in op.bit_operands])
            block.add_op(decode)
            self.values[op.result] = (decode.result,)
            return
        if isinstance(op, SelectOp):
            result_types = _expand_types(result.type for result in op.results)
            select = SelectOp(
                callee=op.callee,
                bit_operands=[self._single(bit) for bit in op.bit_operands],
                cases=dict(op.cases.data),
                case_arguments=self._flatten(op.case_arguments),
                result_types=result_types,
            )
            block.add_op(select)
            self._map_results(op.results, select.results)
            return
        if isinstance(op, ReturnOp):
            block.add_op(ReturnOp(operands=self._flatten(op.operands)))
            return
        raise Rep3BitCompileError(f"unsupported operation {op.name!r}")


def _clone_declaration(op: SelectorOp | DecoderOp) -> SelectorOp | DecoderOp:
    return type(op)(op.sym_name.data, op.input_count)


def compile_rep3_bit(module: ModuleOp) -> ModuleOp:
    """Return a fresh, three-wire encoded kernel-only module."""
    verify_module(module)
    decoder_name = _DECODER
    needs_decoder_declaration = not _has_canonical_decoder(module)
    signatures: dict[str, tuple[list[Attribute], list[Attribute]]] = {}
    for op in module.body.ops:
        if isinstance(op, KernelOp):
            signatures[op.sym_name.data] = (
                _expand_types(op.input_types),
                _expand_types(op.declared_result_types),
            )
    output_ops: list[Operation] = []
    for op in module.body.ops:
        if isinstance(op, (SelectorOp, DecoderOp)):
            output_ops.append(_clone_declaration(op))
        elif isinstance(op, KernelOp):
            output_ops.append(_KernelRewriter(signatures, decoder_name).rewrite(op))
        else:  # pragma: no cover - pre-verification rejects this
            raise Rep3BitCompileError(f"unsupported top-level operation {op.name!r}")
    if needs_decoder_declaration:
        output_ops.append(DecoderOp(decoder_name, _WIDTH))
    output = ModuleOp(output_ops, attributes=dict(module.attributes), sym_name=module.properties.get("sym_name"))
    output.verify()
    verify_module(output)
    return output
