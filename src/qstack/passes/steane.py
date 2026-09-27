"""Lower Clifford kernels into the seven-qubit Steane representation.

Each source qubit becomes an ordered group of seven target qubits.  Fresh
groups are prepared as encoded logical zero; supported Clifford gates act on
the group and are followed by syndrome extraction and conditional correction;
measurement produces seven physical bits and returns one decoded logical bit.

Syndrome extraction and correction are emitted as private helper kernels.  A
selector chooses the correction kernel from the three-bit syndrome, while a
decoder converts physical measurement results to the source program's bit.
Each pass invocation creates its own declarations and helper symbols.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr
from xdsl.ir import Block, Operation, Region, SSAValue

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, HOp, XOp, ZOp
from qstack.dialect.core import (
    CallOp,
    DecodeOp,
    DecoderOp,
    KernelOp,
    MeasureOp,
    ReturnOp,
    SelectOp,
    SelectorOp,
)
from qstack.passes.base import (
    Encoding,
    LoweringContext,
    LoweringPass,
    PassError,
    QubitGroup,
    require_qubit_group,
)
from qstack.runtime.registry import CallbackRegistry

logger = logging.getLogger("qstack")
_WIDTH = 7
_FAMILY = "steane"
_DECODER_IMPLEMENTATION = f"{_FAMILY}:decode"
_SELECTOR_IMPLEMENTATION = f"{_FAMILY}:syndrome"

# Each tuple is the support of one parity check.  Their order determines both
# the three returned syndrome bits and the keys in _SYNDROME_TABLE.
_STABILIZER_SUPPORTS = ((0, 1, 3, 4), (0, 2, 3, 5), (1, 2, 3, 6))
_SYNDROME_BITS = len(_STABILIZER_SUPPORTS)

# Map each syndrome to the one physical position consistent with that syndrome.
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


class SteaneLoweringError(PassError):
    """Raised when a module is outside the supported Steane fragment."""


def steane_syndrome_label(bits: tuple[int, ...]) -> str:
    """Select the correction case identified by a three-bit Steane syndrome.

    Case labels are strings because they name entries in ``qstack.select``.
    The all-zero syndrome selects the identity case; every other syndrome
    identifies the physical qubit on which the correction acts.
    """
    fault = _SYNDROME_TABLE[tuple(bits)]
    logger.debug("syndrome: %s, correction: %s", tuple(bits), fault)
    return "none" if fault is None else str(fault)


def steane_decode_bits(bits: tuple[int, ...]) -> int:
    """Recover one logical measurement bit from a seven-bit Steane codeword.

    The decoder locates and flips a possible single-bit measurement error,
    then returns the corrected codeword parity used as the logical outcome.
    """
    if len(bits) != _WIDTH:
        raise ValueError(f"Steane decoding expects {_WIDTH} bits, got {len(bits)}")
    corrected = list(bits)
    syndrome = tuple(
        sum(corrected[index] for index in support) % 2
        for support in _STABILIZER_SUPPORTS
    )
    fault = _SYNDROME_TABLE[syndrome]
    if fault is not None:
        corrected[fault] ^= 1
    return sum(corrected) % 2


def _register_callbacks(registry: CallbackRegistry) -> None:
    """Install the stateless implementations shared by all generated layers.

    Layer-qualified declarations resolve to these family-level registry keys,
    so repeated lowering adds declarations without duplicating implementations.
    """
    if not registry.has_decoder(_DECODER_IMPLEMENTATION):
        registry.decoder(_DECODER_IMPLEMENTATION)(steane_decode_bits)
    if not registry.has_selector(_SELECTOR_IMPLEMENTATION):
        registry.selector(_SELECTOR_IMPLEMENTATION)(steane_syndrome_label)


class SteaneLowering(LoweringPass):
    """Realize each source qubit as a seven-qubit Steane group.

    The pass prepares encoded zero at kernel allocation boundaries, applies the
    supported logical Cliffords transversally, and inserts error correction
    after each logical gate.  Logical measurement is implemented by measuring
    every qubit in the group and invoking the generated decoder.
    """

    pass_id = "qstack.steane"
    preserve_unhandled_operations = False
    encoding = Encoding(1, _WIDTH)

    def error(self, context: LoweringContext, message: str) -> PassError:
        return SteaneLoweringError(str(super().error(context, message)))

    def prepare_run(self, module: ModuleOp) -> LoweringContext:
        """Create the declarations and helper kernels used by this pass layer.

        Generated names include the global pass index because helpers from an
        earlier Steane layer are themselves lowered by later passes, while the
        new layer still needs helpers at its own target representation.
        """
        context = super().prepare_run(module)
        source = f"{_FAMILY}.{context.pass_index}"
        stem = f"__qstack_steane_{context.pass_index}"

        # Handlers use these roles to call the correct helper without rebuilding
        # or duplicating its generated symbol name.
        context.data.update(
            bit=f"{stem}_bit_syndrome",
            phase=f"{stem}_phase_syndrome",
            identity=f"{stem}_identity",
            x=f"{stem}_correct_x_",
            z=f"{stem}_correct_z_",
        )
        names = context.data

        # Decoder and selector share one callback source because they are
        # introduced together as the classical boundary of this Steane layer.
        context.compiler_callbacks.update(
            decoder=DecoderOp(f"{source}:decode", _WIDTH),
            syndrome=SelectorOp(f"{source}:syndrome", _SYNDROME_BITS),
        )

        # Syndrome kernels return their three measured ancillas followed by the
        # still-live data group.  Correction kernels preserve that group while
        # applying either no gate or one physical X/Z correction.
        helper_kernels = [
            _syndrome_kernel(names["bit"], phase=False),
            _syndrome_kernel(names["phase"], phase=True),
            _correction_kernel(names["identity"]),
        ]
        helper_kernels.extend(
            _correction_kernel(f"{names['x']}{index}", XOp, index)
            for index in range(_WIDTH)
        )
        helper_kernels.extend(
            _correction_kernel(f"{names['z']}{index}", ZOp, index)
            for index in range(_WIDTH)
        )
        context.helper_kernels.extend(helper_kernels)
        return context

    def operation_handlers(self):
        return {
            HOp: self._lower_one_qubit,
            XOp: self._lower_one_qubit,
            ZOp: self._lower_one_qubit,
            CxOp: self._lower_cx,
        }

    def prepare_encoded_zero(self, target_value, context):
        """Prepare the seven fresh target qubits as Steane logical zero."""
        group = require_qubit_group(
            target_value, pass_=self, context=context, description="fresh qubit"
        )
        operations, outputs = _prepare_zero(group.qubits)
        return operations, (QubitGroup(outputs),)

    def _lower_one_qubit(self, source, operands, context):
        """Apply a supported one-qubit Clifford across the group, then correct."""
        operations = []
        transformed = []
        group = require_qubit_group(
            operands[0], pass_=self, context=context, description=source.name
        )
        for value in group.qubits:
            gate = type(source)(value)
            gate.location = source.location
            operations.append(gate)
            transformed.append(gate.result)
        correction_ops, outputs = _error_correct(
            transformed, phase=isinstance(source, ZOp), context=context
        )
        for operation in correction_ops:
            operation.location = source.location
        correction_ops[-1].attributes.update(source.attributes)
        operations.extend(correction_ops)
        return operations, (QubitGroup(outputs),)

    def _lower_cx(self, source, operands, context):
        """Apply pairwise CNOTs and correct the two resulting groups independently."""
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
        control_ops, control_outputs = _error_correct(
            controls, phase=False, context=context
        )
        target_ops, target_outputs = _error_correct(
            targets, phase=False, context=context
        )
        for operation in (*control_ops, *target_ops):
            operation.location = source.location
        target_ops[-1].attributes.update(source.attributes)
        operations.extend((*control_ops, *target_ops))
        return operations, (QubitGroup(control_outputs), QubitGroup(target_outputs))

    def lower_measure(self, source, mapped_operands, context):
        """Measure all seven target qubits and decode one logical result bit."""
        operations = []
        bits = []
        group = require_qubit_group(
            mapped_operands[0],
            pass_=self,
            context=context,
            description="measured qubit",
        )
        for value in group.qubits:
            measure = MeasureOp(operand=value)
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


def _error_correct(
    data: Sequence[SSAValue],
    *,
    phase: bool,
    context: LoweringContext,
) -> tuple[list[Operation], tuple[SSAValue, ...]]:
    """Build syndrome extraction and conditional correction for one qubit group.

    The fragment calls the helper kernel for the requested error basis, then
    dispatches to the correction kernel selected by this run's syndrome
    callback.  It returns the detached operations and the corrected data
    qubits that represent the source operation's result.
    """
    names = context.data
    syndrome = names["phase" if phase else "bit"]
    extract = CallOp(
        syndrome,
        data,
        [BitType(), BitType(), BitType(), *[QubitType() for _ in range(_WIDTH)]],
    )
    correction = names["z" if phase else "x"]
    cases = {
        "none": SymbolRefAttr(names["identity"]),
        **{
            str(index): SymbolRefAttr(f"{correction}{index}")
            for index in range(_WIDTH)
        },
    }
    selector = context.compiler_callbacks["syndrome"]
    assert isinstance(selector, SelectorOp)
    select = SelectOp(
        callee=selector.sym_name.data,
        bit_operands=extract.results[:3],
        cases=cases,
        case_arguments=extract.results[3:],
        result_types=[QubitType() for _ in range(_WIDTH)],
    )
    return [extract, select], tuple(select.results)


def _prepare_zero(
    values: Sequence[SSAValue],
) -> tuple[list[Operation], tuple[SSAValue, ...]]:
    """Build the encoding circuit for logical zero from seven physical zeros.

    Qubits 4, 5, and 6 parameterize the classical generator words in
    superposition.  The CNOT fanout computes those words into the remaining
    positions, producing the Steane logical-zero codeword.  The operations stay
    detached so the kernel driver can record and append the preparation circuit.
    """
    operations = []
    current = list(values)

    # Put the three generator qubits into an equal superposition.
    for index in (4, 5, 6):
        gate = HOp(current[index])
        operations.append(gate)
        current[index] = gate.result

    # Fan each generator bit into the positions selected by its codeword row.
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
        gate = CxOp(current[control], current[target])
        operations.append(gate)
        current[control], current[target] = gate.control_out, gate.target_out
    return operations, tuple(current)


def _syndrome_kernel(name: str, *, phase: bool) -> KernelOp:
    """Build a helper that extracts one three-bit syndrome without consuming data.

    The kernel allocates three ancillas and borrows the seven data qubits.  For
    bit-error extraction, data controls the ancillas.  For phase-error
    extraction, Hadamards prepare and measure the ancillas in the X basis, and
    the CNOT direction is reversed.  The kernel returns the measured syndrome
    before the updated data group so ``_error_correct`` can feed both directly
    to ``qstack.select``.
    """
    block = Block(
        arg_types=[
            QubitType(),
            QubitType(),
            QubitType(),
            *[QubitType() for _ in range(_WIDTH)],
        ]
    )
    ancillas = list(block.args[:3])
    data = list(block.args[3:])

    if phase:
        for index, ancilla in enumerate(ancillas):
            gate = HOp(ancilla)
            block.add_op(gate)
            ancillas[index] = gate.result
        for ancilla_index, support in enumerate(_STABILIZER_SUPPORTS):
            for data_index in support:
                gate = CxOp(ancillas[ancilla_index], data[data_index])
                block.add_op(gate)
                ancillas[ancilla_index], data[data_index] = (
                    gate.control_out,
                    gate.target_out,
                )
        for index, ancilla in enumerate(ancillas):
            gate = HOp(ancilla)
            block.add_op(gate)
            ancillas[index] = gate.result
    else:
        for ancilla_index, support in enumerate(_STABILIZER_SUPPORTS):
            for data_index in support:
                gate = CxOp(data[data_index], ancillas[ancilla_index])
                block.add_op(gate)
                data[data_index], ancillas[ancilla_index] = (
                    gate.control_out,
                    gate.target_out,
                )

    # Measurement consumes the ancillas; the data qubits remain live results.
    bits = []
    for ancilla in ancillas:
        measure = MeasureOp(operand=ancilla)
        block.add_op(measure)
        bits.append(measure.result)
    block.add_op(ReturnOp(operands=[*bits, *data]))
    return KernelOp(
        name,
        input_types=[QubitType() for _ in range(_WIDTH)],
        result_types=[
            BitType(),
            BitType(),
            BitType(),
            *[QubitType() for _ in range(_WIDTH)],
        ],
        allocates=3,
        region=Region([block]),
    )


def _correction_kernel(name: str, gate_type=None, index: int | None = None) -> KernelOp:
    """Build one selector case that preserves or corrects a Steane group.

    Omitting the gate and index produces the identity case.  Otherwise the
    kernel applies the requested Pauli to one physical position and returns the
    entire group in its original order.
    """
    block = Block(arg_types=[QubitType() for _ in range(_WIDTH)])
    values = list(block.args)
    if gate_type is not None and index is not None:
        gate = gate_type(values[index])
        block.add_op(gate)
        values[index] = gate.result
    block.add_op(ReturnOp(operands=values))
    return KernelOp(
        name,
        input_types=[QubitType() for _ in range(_WIDTH)],
        result_types=[QubitType() for _ in range(_WIDTH)],
        allocates=0,
        region=Region([block]),
    )


def lower_steane(module: ModuleOp, registry: CallbackRegistry) -> ModuleOp:
    """Return a Steane-lowered module and install its callback implementations."""
    output = SteaneLowering().run(module)
    _register_callbacks(registry)
    return output
