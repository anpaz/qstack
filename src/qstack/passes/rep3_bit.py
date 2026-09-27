"""Lower Clifford kernels into a three-qubit bit repetition representation.

Each source qubit becomes an ordered group of three target qubits.  A fresh
group already represents logical zero as ``|000>`` and therefore needs no
preparation circuit.  Supported gates are reproduced at each corresponding
position in the group.

Measurement consumes all three physical qubits and passes their results to a
majority-vote decoder, which returns the one source-level bit.  This pass does
not emit syndrome-extraction or active-correction kernels; the repetition code
is decoded only at the measurement boundary.
"""

from __future__ import annotations

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Operation

from qstack.dialect import QubitType
from qstack.dialect.cliffords import CxOp, CzOp, HOp, SOp, XOp, ZOp
from qstack.dialect.core import DecodeOp, DecoderOp, MeasureOp
from qstack.passes.base import (
    Encoding,
    LoweringContext,
    LoweringPass,
    PassError,
    QubitGroup,
    require_qubit_group,
)
from qstack.runtime.registry import CallbackRegistry

_WIDTH = 3
_FAMILY = "rep3_bit"
_IMPLEMENTATION = f"{_FAMILY}:decode"


class Rep3BitLoweringError(PassError):
    """Raised when a module is outside the supported bit-code fragment."""


def _majority_vote(bits: tuple[int, ...]) -> int:
    """Decode three physical measurement outcomes as their majority value."""
    return int(sum(bits) >= 2)


def _register_callbacks(registry: CallbackRegistry) -> None:
    """Install the stateless decoder implementation shared by all pass layers.

    Each layer emits its own qualified decoder declaration, but registry lookup
    removes the layer component and resolves all of them to this implementation.
    """
    if not registry.has_decoder(_IMPLEMENTATION):
        registry.decoder(_IMPLEMENTATION)(_majority_vote)


class Rep3BitLowering(LoweringPass):
    """Represent each source qubit in the three-qubit computational-basis code.

    The declared encoding widens kernel signatures and allocations.  Fresh
    target qubits need no additional preparation because their initial
    ``|000>`` state represents source ``|0>``; source ``|1>`` is represented
    by ``|111>``, with superpositions extended linearly.  Operation handlers
    transform all three corresponding target values, while ``lower_measure``
    collapses the three physical results back to one bit.
    """

    pass_id = "qstack.rep3-bit"
    preserve_unhandled_operations = False
    encoding = Encoding(1, _WIDTH)

    def error(self, context: LoweringContext, message: str) -> PassError:
        return Rep3BitLoweringError(str(super().error(context, message)))

    def prepare_run(self, module: ModuleOp) -> LoweringContext:
        """Updates the context with the decoder callback declaration"""
        context = super().prepare_run(module)
        decoder = f"{_FAMILY}.{context.pass_index}:decode"
        context.compiler_callbacks["decoder"] = DecoderOp(decoder, _WIDTH)
        return context

    def operation_handlers(self):
        """Map every gate supported by this lowering to a group-wise handler."""
        return {
            HOp: self._lower_one_qubit,
            XOp: self._lower_one_qubit,
            ZOp: self._lower_one_qubit,
            SOp: self._lower_one_qubit,
            CxOp: self._lower_two_qubit,
            CzOp: self._lower_two_qubit,
        }

    def _clone_gate(self, source: Operation, operands, result_count: int):
        """Rebuild ``source`` for one position while preserving its metadata."""
        return type(source).create(
            operands=operands,
            result_types=[QubitType() for _ in range(result_count)],
            properties=dict(source.properties),
            attributes=dict(source.attributes),
            location=source.location,
        )

    def _lower_one_qubit(self, source, operands, context):
        """Apply a one-qubit source gate independently at all three positions."""
        operations = []
        outputs = []
        group = require_qubit_group(
            operands[0], pass_=self, context=context, description=source.name
        )
        for qubit in group.qubits:
            target = self._clone_gate(source, [qubit], 1)
            operations.append(target)
            outputs.append(target.results[0])
        return operations, (QubitGroup(tuple(outputs)),)

    def _lower_two_qubit(self, source, operands, context):
        """Apply a two-qubit source gate to corresponding positions in two groups."""
        operations = []
        first = []
        second = []
        control_group = require_qubit_group(
            operands[0], pass_=self, context=context, description="control"
        )
        target_group = require_qubit_group(
            operands[1], pass_=self, context=context, description="target"
        )
        for control, target_value in zip(
            control_group.qubits, target_group.qubits, strict=True
        ):
            target = self._clone_gate(source, [control, target_value], 2)
            operations.append(target)
            first.append(target.results[0])
            second.append(target.results[1])
        return operations, (QubitGroup(tuple(first)), QubitGroup(tuple(second)))

    def lower_measure(self, source, mapped_operands, context):
        """Measure the group and decode its three outcomes to one logical bit."""
        operations = []
        bits = []
        group = require_qubit_group(
            mapped_operands[0],
            pass_=self,
            context=context,
            description="measured qubit",
        )
        for qubit in group.qubits:
            measure = MeasureOp(operand=qubit)
            measure.location = source.location
            operations.append(measure)
            bits.append(measure.result)
        decoder = context.compiler_callbacks["decoder"]
        assert isinstance(decoder, DecoderOp)
        decode = DecodeOp(callee=decoder.sym_name.data, bit_operands=bits)
        decode.location = source.location
        decode.attributes.update(source.attributes)
        operations.append(decode)
        return operations, (decode.result,)


def lower_rep3_bit(module: ModuleOp, registry: CallbackRegistry) -> ModuleOp:
    """Return a bit-repetition-lowered module and install its decoder."""
    output = Rep3BitLowering().run(module)
    _register_callbacks(registry)
    return output
