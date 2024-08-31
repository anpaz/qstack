import math

import runtimes.matrix.instruction_set as matrix

from qcir.circuit import Circuit, Comment, Instruction


def handle_mz(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix_mz",
        [
            matrix.Measure(targets=inst.targets),
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
        "matrix:prepare_bell",
        [
            Comment("start: " + inst.name),
            matrix.Matrix1(parameters=H, targets=[inst.targets[0]]),
            matrix.Matrix2(parameters=CX, targets=[inst.targets[0], inst.targets[1]]),
        ],
    )


def handle_prepare_zero(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix:|0>",
        [],
    )


def handle_hadamard(inst: Instruction) -> Circuit:
    # fmt: off
    sqrt1_2 = math.sqrt(1. / 2.)
    H = [
        sqrt1_2,  sqrt1_2,
        sqrt1_2, -sqrt1_2,
    ]
    # fmt: on
    return Circuit(
        "matrix:hadamard",
        [
            Comment("start: " + inst.name),
            matrix.Matrix1(parameters=H, targets=[inst.targets[0]]),
        ],
    )


def handle_ctrlx(inst: Instruction):
    # fmt: off
    CX = [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 1.0, 
        0.0, 0.0, 1.0, 0.0,
    ]
    # fmt: on
    return Circuit(
        "matrix:ctrlx",
        [
            Comment("start: " + inst.name),
            matrix.Matrix2(parameters=CX, targets=[inst.targets[0], inst.targets[1]]),
        ],
    )
