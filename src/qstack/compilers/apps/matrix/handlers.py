import math

import qstack.layers.matrix.instruction_set as matrix

from qstack.circuit import Circuit, Comment, Instruction


def handle_prepare_zero(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix:|0>",
        [],
    )


def handle_prepare_one(inst: Instruction) -> Circuit:
    # fmt: off
    X = [
        0, 1,
        1, 0,
    ]
    # fmt: on
    return Circuit(
        "matrix:|1>",
        [
            Comment("start: " + inst.name),
            matrix.Matrix1(parameters=X, targets=[inst.targets[0]]),
        ],
    )


def handle_prepare_random(inst: Instruction) -> Circuit:
    # fmt: off
    sqrt1_2 = math.sqrt(1. / 2.)
    H = [
        sqrt1_2,  sqrt1_2,
        sqrt1_2, -sqrt1_2,
    ]
    # fmt: on
    return Circuit(
        "matrix:|random>",
        [
            Comment("start: " + inst.name),
            matrix.Matrix1(parameters=H, targets=[inst.targets[0]]),
        ],
    )


def handle_prepare_bell(inst: Instruction) -> Circuit:
    # fmt: off
    sqrt1_2 = math.sqrt(1. / 2.)
    H = [
        sqrt1_2,  sqrt1_2,
        sqrt1_2, -sqrt1_2,
    ]
    CX = [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 1.0, 
        0.0, 0.0, 1.0, 0.0,
    ]
    # fmt: on
    return Circuit(
        "matrix:|bell>",
        [
            Comment("start: " + inst.name),
            matrix.Matrix1(parameters=H, targets=[inst.targets[0]]),
            matrix.Matrix2(parameters=CX, targets=[inst.targets[0], inst.targets[1]]),
        ],
    )


def handle_measure(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix_mz",
        [
            matrix.Measure(targets=inst.targets),
        ],
    )
