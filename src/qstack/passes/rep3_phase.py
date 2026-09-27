"""Lower Clifford kernels into a three-qubit phase repetition representation.

Each source qubit becomes an ordered group of three target qubits.  Fresh
physical zeros are rotated into ``|+++>``, the representation of logical zero.
The handlers implement the pass's supported gates with group-level Clifford
fragments rather than by copying every source operation directly.

Measurement rotates each physical qubit from the X basis to the computational
basis, measures all three, and returns their majority value as one source-level
bit.  The pass performs no separate syndrome extraction or active correction.
"""

from __future__ import annotations

from xdsl.dialects.builtin import ModuleOp

from qstack.dialect.cliffords import CxOp, CzOp, HOp, XOp, ZOp
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
_FAMILY = "rep3_phase"
_IMPLEMENTATION = f"{_FAMILY}:decode"


class Rep3PhaseLoweringError(PassError):
    """Raised when a module is outside the supported phase-code fragment."""


def _majority_vote(bits: tuple[int, ...]) -> int:
    """Decode three X-basis measurement outcomes as their majority value."""
    return int(sum(bits) >= 2)


def _register_callbacks(registry: CallbackRegistry) -> None:
    """Install the stateless decoder implementation shared by all pass layers.

    Each layer emits its own qualified decoder declaration, but registry lookup
    removes the layer component and resolves all of them to this implementation.
    """
    if not registry.has_decoder(_IMPLEMENTATION):
        registry.decoder(_IMPLEMENTATION)(_majority_vote)


class Rep3PhaseLowering(LoweringPass):
    """Represent each source qubit in the three-qubit X-basis code.

    The declared encoding widens kernel signatures and allocations.  Preparing
    fresh groups establishes ``|+++>`` as represented source ``|0>``;
    ``|--->`` represents source ``|1>``, with superpositions extended linearly.
    Dedicated handlers maintain the ordered three-value group, and measurement
    returns to the computational basis for majority decoding.
    """

    pass_id = "qstack.rep3-phase"
    preserve_unhandled_operations = False
    encoding = Encoding(1, _WIDTH)

    def error(self, context: LoweringContext, message: str) -> PassError:
        return Rep3PhaseLoweringError(str(super().error(context, message)))

    def prepare_run(self, module: ModuleOp) -> LoweringContext:
        """Create the decoder declaration owned by this pass invocation.

        Its source contains the global pass index, keeping declarations from
        composed repetition layers distinct while they share one registered
        implementation.
        """
        context = super().prepare_run(module)
        decoder = f"{_FAMILY}.{context.pass_index}:decode"
        context.compiler_callbacks["decoder"] = DecoderOp(decoder, _WIDTH)
        return context

    def operation_handlers(self):
        """Return the source operations with defined phase-code fragments."""
        return {
            XOp: self._lower_x,
            HOp: self._lower_h,
            CxOp: self._lower_cx,
        }

    def prepare_encoded_zero(self, target_value, context):
        """Rotate three fresh physical zeros into the encoded ``|+++>`` state."""
        operations = []
        outputs = []
        group = require_qubit_group(
            target_value, pass_=self, context=context, description="fresh qubit"
        )
        for qubit in group.qubits:
            gate = HOp(qubit)
            operations.append(gate)
            outputs.append(gate.result)
        return operations, (QubitGroup(tuple(outputs)),)

    def _lower_x(self, source, operands, context):
        """Implement source X by applying Z to every X-basis component."""
        operations = []
        outputs = []
        group = require_qubit_group(
            operands[0], pass_=self, context=context, description=source.name
        )
        for qubit in group.qubits:
            gate = ZOp(qubit)
            gate.location = source.location
            operations.append(gate)
            outputs.append(gate.result)
        operations[-1].attributes.update(source.attributes)
        return operations, (QubitGroup(tuple(outputs)),)

    def _lower_h(self, source, operands, context):
        """Implement source H with the pass's H-CZ-CZ three-qubit fragment."""
        group = require_qubit_group(
            operands[0], pass_=self, context=context, description=source.name
        )
        q0, q1, q2 = group.qubits
        h = HOp(q0)
        first = CzOp(h.result, q1)
        second = CzOp(first.control_out, q2)
        for operation in (h, first, second):
            operation.location = source.location
        second.attributes.update(source.attributes)

        # Reversing the outer positions completes this fragment's wire mapping;
        # later handlers receive the values in their new representation order.
        return (
            [h, first, second],
            (QubitGroup((second.target_out, first.target_out, second.control_out)),),
        )

    def _lower_cx(self, source, operands, context):
        """Apply CNOT between corresponding positions in two encoded groups."""
        operations = []
        controls = []
        targets = []
        control_group = require_qubit_group(
            operands[0], pass_=self, context=context, description="control"
        )
        target_group = require_qubit_group(
            operands[1], pass_=self, context=context, description="target"
        )
        for control, target_value in zip(
            control_group.qubits, target_group.qubits, strict=True
        ):
            gate = CxOp(control, target_value)
            gate.location = source.location
            operations.append(gate)
            controls.append(gate.control_out)
            targets.append(gate.target_out)
        operations[-1].attributes.update(source.attributes)
        return operations, (QubitGroup(tuple(controls)), QubitGroup(tuple(targets)))

    def lower_measure(self, source, mapped_operands, context):
        """Measure in the X basis and decode three outcomes to one logical bit."""
        operations = []
        bits = []
        group = require_qubit_group(
            mapped_operands[0],
            pass_=self,
            context=context,
            description="measured qubit",
        )
        for qubit in group.qubits:
            basis = HOp(qubit)
            measure = MeasureOp(operand=basis.result)
            basis.location = measure.location = source.location
            operations.extend((basis, measure))
            bits.append(measure.result)
        decoder = context.compiler_callbacks["decoder"]
        assert isinstance(decoder, DecoderOp)
        decode = DecodeOp(callee=decoder.sym_name.data, bit_operands=bits)
        decode.location = source.location
        decode.attributes.update(source.attributes)
        operations.append(decode)
        return operations, (decode.result,)


def lower_rep3_phase(module: ModuleOp, registry: CallbackRegistry) -> ModuleOp:
    """Return a phase-repetition-lowered module and install its decoder."""
    output = Rep3PhaseLowering().run(module)
    _register_callbacks(registry)
    return output
