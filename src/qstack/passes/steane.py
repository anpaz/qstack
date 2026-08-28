"""Kernel-only Steane [[7,1,3]] lowering."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr
from xdsl.ir import Attribute, Block, Operation, Region, SSAValue

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, HOp, XOp, ZOp
from qstack.dialect.core import CallOp, DecodeOp, DecoderOp, KernelOp, MeasureOp, ReturnOp, SelectOp, SelectorOp
from qstack.verifier import verify_module

logger = logging.getLogger("qstack")
_WIDTH = 7
_PREFIX = "__qstack_steane_"
_DECODER = "__qstack_steane_decode"
_SELECTOR = "__qstack_steane_syndrome"
_STABILIZER_SUPPORTS = ((0, 1, 3, 4), (0, 2, 3, 5), (1, 2, 3, 6))
_SYNDROME_BITS = len(_STABILIZER_SUPPORTS)
_SYNDROME_TABLE = {
    (0, 0, 0): None, (0, 0, 1): 6, (0, 1, 0): 5, (0, 1, 1): 3,
    (1, 0, 0): 4, (1, 0, 1): 2, (1, 1, 0): 1, (1, 1, 1): 0,
}


class SteaneCompileError(Exception):
    """Raised when a module cannot be lowered to the supported Steane fragment."""


def steane_syndrome_label(bits: tuple[int, ...]) -> str:
    fault = _SYNDROME_TABLE[tuple(bits)]
    logger.debug("syndrome: %s, correction: %s", tuple(bits), fault)
    return "none" if fault is None else str(fault)


def steane_decode_bits(bits: tuple[int, ...]) -> int:
    if len(bits) != _WIDTH:
        raise ValueError(f"Steane decoding expects {_WIDTH} bits, got {len(bits)}")
    corrected = list(bits)
    syndrome = tuple(sum(corrected[index] for index in support) % 2 for support in _STABILIZER_SUPPORTS)
    fault = _SYNDROME_TABLE[syndrome]
    if fault is not None:
        corrected[fault] ^= 1
    return sum(corrected) % 2


def _layer_names(module: ModuleOp) -> dict[str, str]:
    """Fresh names for quantum helper kernels; callback symbols stay canonical."""
    symbols = {op.sym_name.data for op in module.body.ops if hasattr(op, "sym_name")}
    index = 0
    while f"{_PREFIX}{index}_bit_syndrome" in symbols:
        index += 1
    stem = f"{_PREFIX}{index}"
    return {
        "decoder": _DECODER,
        "selector": _SELECTOR,
        "bit": f"{stem}_bit_syndrome",
        "phase": f"{stem}_phase_syndrome",
        "identity": f"{stem}_identity",
        "x": f"{stem}_correct_x_",
        "z": f"{stem}_correct_z_",
    }


def _expand_type(typ: Attribute) -> list[Attribute]:
    return [QubitType() for _ in range(_WIDTH)] if isinstance(typ, QubitType) else [typ]


def _expand_types(types: Iterable[Attribute]) -> list[Attribute]:
    return [result for typ in types for result in _expand_type(typ)]


def register_steane_callbacks(registry) -> None:
    """Install the canonical Steane decoder and syndrome selector."""
    if not registry.has_decoder(_DECODER):
        registry.decoder(_DECODER)(steane_decode_bits)
    if not registry.has_selector(_SELECTOR):
        registry.selector(_SELECTOR)(steane_syndrome_label)


def _has_canonical_callback(
    module: ModuleOp,
    name: str,
    callback_type: type[DecoderOp] | type[SelectorOp],
    arity: int,
) -> bool:
    for op in module.body.ops:
        if not hasattr(op, "sym_name") or op.sym_name.data != name:
            continue
        if isinstance(op, callback_type) and op.input_count == arity:
            return True
        raise SteaneCompileError(f"reserved callback symbol @{name} has an incompatible declaration")
    return False


def _prepare_zero(block: Block, values: Sequence[SSAValue]) -> tuple[SSAValue, ...]:
    current = list(values)
    for index in (4, 5, 6):
        gate = HOp(current[index]); block.add_op(gate); current[index] = gate.result
    for control, target in ((4, 0), (4, 1), (4, 3), (5, 0), (5, 2), (5, 3), (6, 1), (6, 2), (6, 3)):
        gate = CxOp(current[control], current[target]); block.add_op(gate)
        current[control], current[target] = gate.control_out, gate.target_out
    return tuple(current)


class _Rewriter:
    def __init__(self, signatures: dict[str, tuple[list[Attribute], list[Attribute]]], names: dict[str, str]):
        self.signatures = signatures
        self.names = names
        self.values: dict[SSAValue, tuple[SSAValue, ...]] = {}

    def rewrite(self, source: KernelOp) -> KernelOp:
        inputs, results = self.signatures[source.sym_name.data]
        block = Block(arg_types=[*inputs, *[QubitType() for _ in range(source.allocation_count * _WIDTH)]])
        self._map(source.body.block.args, block.args)
        for fresh in source.body.block.args[len(source.input_types) :]:
            self.values[fresh] = _prepare_zero(block, self.values[fresh])
        for op in source.body.block.ops:
            self._rewrite_op(op, block)
        return KernelOp(source.sym_name.data, input_types=inputs, result_types=results,
                        allocates=source.allocation_count * _WIDTH, region=Region([block]))

    def _map(self, old: Sequence[SSAValue], new: Sequence[SSAValue]) -> None:
        cursor = 0
        for value in old:
            width = _WIDTH if isinstance(value.type, QubitType) else 1
            self.values[value] = tuple(new[cursor:cursor + width]); cursor += width

    def _values(self, value: SSAValue) -> tuple[SSAValue, ...]:
        try: return self.values[value]
        except KeyError as exc: raise SteaneCompileError(f"no rewritten value for {value!r}") from exc

    def _single(self, value: SSAValue) -> SSAValue:
        values = self._values(value)
        if len(values) != 1: raise SteaneCompileError(f"expected scalar bit for {value!r}")
        return values[0]

    def _flatten(self, values: Iterable[SSAValue]) -> list[SSAValue]:
        return [new for value in values for new in self._values(value)]

    def _error_correct(self, block: Block, data: Sequence[SSAValue], *, phase: bool) -> tuple[SSAValue, ...]:
        syndrome = self.names["phase" if phase else "bit"]
        extract = CallOp(syndrome, data, [BitType(), BitType(), BitType(), *[QubitType() for _ in range(_WIDTH)]])
        block.add_op(extract)
        correction = self.names["z" if phase else "x"]
        cases = {"none": SymbolRefAttr(self.names["identity"]), **{str(i): SymbolRefAttr(f"{correction}{i}") for i in range(_WIDTH)}}
        select = SelectOp(callee=self.names["selector"],
                          bit_operands=extract.results[:3], cases=cases,
                          case_arguments=extract.results[3:], result_types=[QubitType() for _ in range(_WIDTH)])
        block.add_op(select)
        return tuple(select.results)

    def _rewrite_op(self, op: Operation, block: Block) -> None:
        if isinstance(op, (HOp, XOp, ZOp)):
            transformed: list[SSAValue] = []
            for value in self._values(op.operands[0]):
                gate = type(op)(value); block.add_op(gate); transformed.append(gate.result)
            self.values[op.results[0]] = self._error_correct(block, transformed, phase=isinstance(op, ZOp))
            return
        if isinstance(op, CxOp):
            controls: list[SSAValue] = []; targets: list[SSAValue] = []
            for control, target in zip(self._values(op.control), self._values(op.target), strict=True):
                gate = CxOp(control, target); block.add_op(gate); controls.append(gate.control_out); targets.append(gate.target_out)
            self.values[op.control_out] = self._error_correct(block, controls, phase=False)
            self.values[op.target_out] = self._error_correct(block, targets, phase=False)
            return
        if isinstance(op, MeasureOp):
            bits: list[SSAValue] = []
            for value in self._values(op.qubit):
                measure = MeasureOp(operand=value); block.add_op(measure); bits.append(measure.result)
            decode = DecodeOp(callee=self.names["decoder"], bit_operands=bits); block.add_op(decode)
            self.values[op.result] = (decode.result,)
            return
        if isinstance(op, CallOp):
            _, result_types = self.signatures[op.callee.root_reference.data]
            call = CallOp(op.callee, self._flatten(op.arguments), result_types); block.add_op(call); self._map(op.results, call.results); return
        if isinstance(op, DecodeOp):
            decode = DecodeOp(callee=op.callee, bit_operands=[self._single(bit) for bit in op.bit_operands]); block.add_op(decode); self.values[op.result] = (decode.result,); return
        if isinstance(op, SelectOp):
            select = SelectOp(callee=op.callee,
                              bit_operands=[self._single(bit) for bit in op.bit_operands], cases=dict(op.cases.data),
                              case_arguments=self._flatten(op.case_arguments), result_types=_expand_types(result.type for result in op.results))
            block.add_op(select); self._map(op.results, select.results); return
        if isinstance(op, ReturnOp):
            block.add_op(ReturnOp(operands=self._flatten(op.operands))); return
        raise SteaneCompileError(f"unsupported operation {op.name!r}")


def _syndrome_kernel(name: str, *, phase: bool) -> KernelOp:
    block = Block(arg_types=[*[QubitType() for _ in range(_WIDTH)], QubitType(), QubitType(), QubitType()])
    data = list(block.args[:_WIDTH]); ancillas = list(block.args[_WIDTH:])
    if phase:
        for i, ancilla in enumerate(ancillas):
            gate = HOp(ancilla); block.add_op(gate); ancillas[i] = gate.result
        for ancilla_index, support in enumerate(_STABILIZER_SUPPORTS):
            for data_index in support:
                gate = CxOp(ancillas[ancilla_index], data[data_index]); block.add_op(gate)
                ancillas[ancilla_index], data[data_index] = gate.control_out, gate.target_out
        for i, ancilla in enumerate(ancillas):
            gate = HOp(ancilla); block.add_op(gate); ancillas[i] = gate.result
    else:
        for ancilla_index, support in enumerate(_STABILIZER_SUPPORTS):
            for data_index in support:
                gate = CxOp(data[data_index], ancillas[ancilla_index]); block.add_op(gate)
                data[data_index], ancillas[ancilla_index] = gate.control_out, gate.target_out
    bits: list[SSAValue] = []
    for ancilla in ancillas:
        measure = MeasureOp(operand=ancilla); block.add_op(measure); bits.append(measure.result)
    block.add_op(ReturnOp(operands=[*bits, *data]))
    return KernelOp(name, input_types=[QubitType() for _ in range(_WIDTH)],
                    result_types=[BitType(), BitType(), BitType(), *[QubitType() for _ in range(_WIDTH)]], allocates=3,
                    region=Region([block]))


def _correction_kernel(name: str, gate_type=None, index: int | None = None) -> KernelOp:
    block = Block(arg_types=[QubitType() for _ in range(_WIDTH)]); values = list(block.args)
    if gate_type is not None and index is not None:
        gate = gate_type(values[index]); block.add_op(gate); values[index] = gate.result
    block.add_op(ReturnOp(operands=values))
    return KernelOp(name, input_types=[QubitType() for _ in range(_WIDTH)], result_types=[QubitType() for _ in range(_WIDTH)], allocates=0, region=Region([block]))


def compile_steane(module: ModuleOp) -> ModuleOp:
    verify_module(module)
    names = _layer_names(module)
    needs_decoder_declaration = not _has_canonical_callback(
        module, _DECODER, DecoderOp, _WIDTH
    )
    needs_selector_declaration = not _has_canonical_callback(
        module, _SELECTOR, SelectorOp, _SYNDROME_BITS
    )
    signatures = {
        op.sym_name.data: (_expand_types(op.input_types), _expand_types(op.declared_result_types))
        for op in module.body.ops
        if isinstance(op, KernelOp)
    }
    output_ops: list[Operation] = []
    for op in module.body.ops:
        if isinstance(op, (SelectorOp, DecoderOp)):
            output_ops.append(type(op)(op.sym_name.data, op.input_count))
        elif isinstance(op, KernelOp):
            output_ops.append(_Rewriter(signatures, names).rewrite(op))
    if needs_decoder_declaration:
        output_ops.append(DecoderOp(names["decoder"], _WIDTH))
    if needs_selector_declaration:
        output_ops.append(SelectorOp(names["selector"], _SYNDROME_BITS))
    output_ops.extend([
        _syndrome_kernel(names["bit"], phase=False),
        _syndrome_kernel(names["phase"], phase=True),
        _correction_kernel(names["identity"]),
    ])
    output_ops.extend(_correction_kernel(f"{names['x']}{i}", XOp, i) for i in range(_WIDTH))
    output_ops.extend(_correction_kernel(f"{names['z']}{i}", ZOp, i) for i in range(_WIDTH))
    output = ModuleOp(output_ops, attributes=dict(module.attributes), sym_name=module.properties.get("sym_name"))
    output.verify(); verify_module(output)
    return output
