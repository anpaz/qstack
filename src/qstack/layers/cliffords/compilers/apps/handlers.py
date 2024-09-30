import math

import qstack.layers.cliffords.instruction_set as cliffords

from qcir.circuit import Circuit, Comment, Instruction


def handle_prepare_zero(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix:|0>",
        [cliffords.PrepareZero(targets=inst.targets, attributes=inst.attributes)],
    )


def handle_prepare_one(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix:|1>",
        [
            cliffords.PrepareZero(targets=inst.targets, attributes=inst.attributes),
            cliffords.H(targets=inst.targets, attributes=inst.attributes),
            cliffords.S(targets=inst.targets, attributes=inst.attributes),
            cliffords.S(targets=inst.targets, attributes=inst.attributes),
            cliffords.H(targets=inst.targets, attributes=inst.attributes),
        ],
    )


def handle_prepare_random(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix:|random>",
        [
            cliffords.PrepareZero(targets=inst.targets, attributes=inst.attributes),
            cliffords.H(targets=inst.targets, attributes=inst.attributes),
        ],
    )


def handle_prepare_bell(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix:|bell>",
        [
            cliffords.PrepareZero(targets=[inst.targets[0]], attributes=inst.attributes),
            cliffords.PrepareZero(targets=[inst.targets[1]], attributes=inst.attributes),
            cliffords.H(targets=[inst.targets[0]], attributes=inst.attributes),
            cliffords.CX(targets=inst.targets, attributes=inst.attributes),
        ],
    )


def handle_measure(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix_mz",
        [
            cliffords.MeasureZ(targets=inst.targets, attributes=inst.attributes),
        ],
    )
