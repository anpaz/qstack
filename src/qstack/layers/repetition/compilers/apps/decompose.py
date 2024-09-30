import math

import qstack.layers.apps.instruction_set as apps
from qstack.layers.stabilizer.instruction_set import *

from qcir.circuit import Circuit, Comment, Instruction, Tick

import logging

logger = logging.getLogger("qstack")


def handle_prepare_zero(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix:|0>",
        [PrepareZero(targets=inst.targets, attributes=inst.attributes)],
    )


def handle_prepare_one(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix:|1>",
        [
            PrepareZero(targets=inst.targets, attributes=inst.attributes),
            Tick(),
            X(targets=inst.targets, attributes=inst.attributes),
        ],
    )


def handle_prepare_random(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix:|random>",
        [
            PrepareZero(targets=inst.targets, attributes=inst.attributes),
            Tick(),
            H(targets=inst.targets, attributes=inst.attributes),
        ],
    )


def handle_prepare_bell(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix:|bell>",
        [
            PrepareZero(targets=[inst.targets[0]], attributes=inst.attributes),
            PrepareZero(targets=[inst.targets[1]], attributes=inst.attributes),
            Tick(),
            H(targets=[inst.targets[0]], attributes=inst.attributes),
            Tick(),
            CX(targets=inst.targets, attributes=inst.attributes),
        ],
    )


def handle_measure(inst: Instruction) -> Circuit:
    return Circuit(
        "matrix_mz",
        [
            MeasureZ(targets=inst.targets, attributes=inst.attributes),
        ],
    )


def run(circuit: Circuit) -> Circuit:
    handlers = {
        name: handler
        for (gate, handler) in [
            (apps.Measure, handle_measure),
            (apps.PrepareOne, handle_prepare_one),
            (apps.PrepareZero, handle_prepare_zero),
            (apps.PrepareRandom, handle_prepare_random),
            (apps.PrepareBell, handle_prepare_bell),
        ]
        for name in [gate.name] + list(gate.aliases or [])
    }

    # Make sure the circuit in the kernel uses the right instruction set:
    # qstack.compilers.passes.verify_instructions(circuit, source_instruction_set)

    target_circuit = Circuit(circuit.name, [])

    for inst in [inst for inst in circuit.instructions if isinstance(inst, Instruction)]:
        handler = handlers[inst.name]
        target_circuit += handler(inst)

    logger.debug("Decomposed circuit:")
    logger.debug(target_circuit)

    return target_circuit
