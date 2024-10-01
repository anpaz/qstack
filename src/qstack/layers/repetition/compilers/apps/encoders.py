from dataclasses import dataclass
import math

import qstack.layers.stabilizer.instruction_set as cliffords

from qcir.circuit import Circuit, Comment, Instruction, QubitId, RegisterId
from qstack.quantum_kernel import QuantumKernel


class Context:
    def __init__(self, kernel: QuantumKernel, stabilizer: list[list[str]], x_op, z_op):
        # def base_decoder(memory: list[int], corrections):
        #     return tuple(kernel.decoder(memory[: kernel.register_count]))

        self.blocks = {
            QubitId(i): [QubitId(i * 3), QubitId(i * 3 + 1), QubitId(i * 3 + 2)] for i in range(kernel.qubit_count)
        }
        self.next_measurement = kernel.register_count
        self.decoders = []

        self.stabilizer = stabilizer
        self.x_op = x_op
        self.z_op = z_op


def decode_syndrome(syndrome):
    if syndrome == [0, 0]:
        return ["I", "I", "I"]

    if syndrome == [1, 0]:
        return ["I", "X", "I"]

    if syndrome == [0, 1]:
        return ["I", "I", "X"]

    if syndrome == [1, 1]:
        return ["X", "I", "I"]


def update_syndrome_value(value, syndrome, correction):
    for s, c in zip(syndrome, correction):
        if s == c or c == "I" or s == "I":
            pass
        else:
            value += 1
    return value % 2


def multiply(left, right):
    def check_one(l, r):
        if l == "I":
            return r
        if r == "I":
            return l
        if l == r:
            return "I"
        assert False, f"Unexpected: {l}, {r}"

    result = [check_one(l, r) for l, r in zip(left, right)]
    return result


def build_decoder(block: QubitId, registers: list[RegisterId], stabilizer):
    def decoder(memory: list[int], corrections):
        last_correction = corrections[block]
        syndrome = [memory[r.value] for r in registers]

        new_syndrome = [update_syndrome_value(v, s, last_correction) for (v, s) in zip(syndrome, stabilizer)]
        new_correction = decode_syndrome(new_syndrome)

        corrections[block] = multiply(new_correction, last_correction)

    return decoder


def syndrome_extraction(block: QubitId, context: Context):
    targets = context.blocks[block]
    registers = [RegisterId(i + context.next_measurement) for i in range(len(context.stabilizer))]

    inst = [
        cliffords.MeasurePauli(targets=([r] + targets), parameters=s) for r, s in zip(registers, context.stabilizer)
    ]

    decoder = build_decoder(block, registers, context.stabilizer)

    context.next_measurement += len(context.stabilizer)
    context.decoders.append(decoder)

    return inst


def encode_prepare_zero(inst: Instruction, context: Context) -> Circuit:
    targets = context.blocks[inst.targets[0]]
    result = [cliffords.PrepareZero(targets=[q], attributes=inst.attributes) for q in targets]

    return Circuit("encode:|0>", result + syndrome_extraction(inst.targets[0], context))


def encode_x(inst: Instruction, context: Context) -> Circuit:
    targets = context.blocks[inst.targets[0]]
    result = [cliffords.ApplyPauli(targets=targets, parameters=context.x_op, attributes=inst.attributes)]

    return Circuit("encode:x", result + syndrome_extraction(inst.targets[0], context))


def encode_h(inst: Instruction) -> Circuit:
    pass


def encode_cx(inst: Instruction) -> Circuit:
    pass


def encode_measure(inst: Instruction, context: Context) -> Circuit:
    targets = context.blocks[inst.targets[1]]
    register = context.next_measurement
    result = [
        cliffords.MeasurePauli(
            targets=[RegisterId(register)] + targets,
            parameters=context.z_op,
            attributes=inst.attributes,
        )
    ]

    def decoder(memory: list[int], corrections):
        value = memory[register]
        last_correction = corrections[inst.targets[1]]
        updated_value = update_syndrome_value(value, context.z_op, last_correction)

        memory[inst.targets[0].value] = updated_value

    context.next_measurement += 1
    context.decoders.append(decoder)

    return Circuit("encode:mz", result)
