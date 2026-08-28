"""Kernel-only phase-flip repetition-code lowering."""

from __future__ import annotations

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Attribute, Block, Operation, Region, SSAValue

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, YOp, ZOp
from qstack.dialect.core import DecoderOp, KernelOp, MeasureOp, SelectorOp
from qstack.passes.rep3_bit import _KernelRewriter, _clone_declaration, _expand_types
from qstack.verifier import verify_module

_WIDTH = 3
_DECODER = "__qstack_rep3_phase_decode"


class Rep3PhaseCompileError(Exception):
    """Raised for unsupported phase-code operations."""


def _has_canonical_decoder(module: ModuleOp) -> bool:
    for op in module.body.ops:
        if not hasattr(op, "sym_name") or op.sym_name.data != _DECODER:
            continue
        if isinstance(op, DecoderOp) and op.input_count == _WIDTH:
            return True
        raise Rep3PhaseCompileError(f"reserved callback symbol @{_DECODER} has an incompatible declaration")
    return False


def _majority_vote(bits: tuple[int, ...]) -> int:
    return 1 if sum(bits) >= 2 else 0


def register_rep3_phase_callbacks(registry) -> None:
    """Install the canonical phase-code majority decoder."""
    if not registry.has_decoder(_DECODER):
        registry.decoder(_DECODER)(_majority_vote)


class _PhaseRewriter(_KernelRewriter):
    def rewrite(self, source: KernelOp) -> KernelOp:
        inputs, results = self.signatures[source.sym_name.data]
        block = Block(arg_types=[*inputs, *[QubitType() for _ in range(source.allocation_count * _WIDTH)]])
        self._map_values(source.body.block.args, block.args)
        # Fresh logical |0> states are represented as |+++> in the phase code.
        for argument in source.body.block.args[len(source.input_types) :]:
            prepared: list[SSAValue] = []
            for qubit in self._mapped(argument):
                gate = HOp(qubit)
                block.add_op(gate)
                prepared.append(gate.result)
            self.values[argument] = tuple(prepared)
        for op in source.body.block.ops:
            self._rewrite_op(op, block)
        return KernelOp(
            source.sym_name.data,
            input_types=inputs,
            result_types=results,
            allocates=source.allocation_count * _WIDTH,
            region=Region([block]),
        )

    def _rewrite_op(self, op: Operation, block: Block) -> None:
        if isinstance(op, XOp):
            outputs: list[SSAValue] = []
            for qubit in self._mapped(op.qubit):
                gate = ZOp(qubit)
                block.add_op(gate)
                outputs.append(gate.result)
            self.values[op.result] = tuple(outputs)
            return
        if isinstance(op, HOp):
            q0, q1, q2 = self._mapped(op.qubit)
            h = HOp(q0); block.add_op(h)
            first = CzOp(h.result, q1); block.add_op(first)
            second = CzOp(first.control_out, q2); block.add_op(second)
            self.values[op.result] = (second.target_out, first.target_out, second.control_out)
            return
        if isinstance(op, CxOp):
            first: list[SSAValue] = []
            second: list[SSAValue] = []
            for control, target in zip(self._mapped(op.control), self._mapped(op.target), strict=True):
                gate = CxOp(control, target)
                block.add_op(gate)
                first.append(gate.control_out)
                second.append(gate.target_out)
            self.values[op.control_out] = tuple(first)
            self.values[op.target_out] = tuple(second)
            return
        if isinstance(op, MeasureOp):
            bits: list[SSAValue] = []
            for qubit in self._mapped(op.qubit):
                basis = HOp(qubit); block.add_op(basis)
                measure = MeasureOp(operand=basis.result); block.add_op(measure)
                bits.append(measure.result)
            from qstack.dialect.core import DecodeOp

            decode = DecodeOp(callee=self.decoder, bit_operands=bits)
            block.add_op(decode)
            self.values[op.result] = (decode.result,)
            return
        if isinstance(op, (YOp, ZOp, SOp, CzOp)):
            raise Rep3PhaseCompileError(f"phase repetition does not support {op.name}")
        super()._rewrite_op(op, block)


def compile_rep3_phase(module: ModuleOp) -> ModuleOp:
    verify_module(module)
    decoder = _DECODER
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
            output_ops.append(_PhaseRewriter(signatures, decoder).rewrite(op))
    if needs_decoder_declaration:
        output_ops.append(DecoderOp(decoder, _WIDTH))
    output = ModuleOp(output_ops, attributes=dict(module.attributes), sym_name=module.properties.get("sym_name"))
    output.verify()
    verify_module(output)
    return output
