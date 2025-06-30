import logging
import numpy as np
from dataclasses import replace

from ..compiler import Compiler
from ..ast import QuantumInstruction, Kernel, QubitId
from ..instruction_sets import cliffords_min as cliffords
from ..classic_processor import ClassicContext, ClassicDefinition

logger = logging.getLogger("qstack")

## Stabilizers we're using:
#    [1, 1, 0, 1, 1, 0, 0],
#    [1, 0, 1, 1, 0, 1, 0],
#    [0, 1, 1, 1, 0, 0, 1],


def handle_x(inst: QuantumInstruction):
    target = tuple([QubitId(f"{inst.targets[0]}.{i}") for i in range(7)])
    return Kernel(target=None, instructions=[cliffords.X(q) for q in target])


def handle_z(inst: QuantumInstruction):
    target = tuple([QubitId(f"{inst.targets[0]}.{i}") for i in range(7)])
    return Kernel(target=None, instructions=[cliffords.Z(q) for q in target])


def handle_h(inst: QuantumInstruction):
    target = tuple([QubitId(f"{inst.targets[0]}.{i}") for i in range(7)])
    return Kernel(target=None, instructions=[cliffords.H(q) for q in target])


def handle_cx(inst: QuantumInstruction):
    ctrl = tuple([QubitId(f"{inst.targets[0]}.{i}") for i in range(7)])
    target = tuple([QubitId(f"{inst.targets[1]}.{i}") for i in range(7)])

    return Kernel(target=None, instructions=[cliffords.CX(c, t) for (c, t) in zip(ctrl, target)])


def handle_prepare_zero(t: QubitId):
    q = tuple([QubitId(f"{t}.{i}") for i in range(7)])

    ## Stabilizers we're using:
    #    [1, 1, 0, 1, 1, 0, 0],
    #    [1, 0, 1, 1, 0, 1, 0],
    #    [0, 1, 1, 1, 0, 0, 1],

    instructions = [
        cliffords.H(q[4]),
        cliffords.H(q[5]),
        cliffords.H(q[6]),
        cliffords.CX(q[4], q[0]),
        cliffords.CX(q[4], q[1]),
        cliffords.CX(q[4], q[3]),
        cliffords.CX(q[5], q[0]),
        cliffords.CX(q[5], q[2]),
        cliffords.CX(q[5], q[3]),
        cliffords.CX(q[6], q[1]),
        cliffords.CX(q[6], q[2]),
        cliffords.CX(q[6], q[3]),
    ]

    return Kernel(target=None, instructions=instructions)


def x_syndrome_extraction(t: QubitId):
    target = tuple([QubitId(f"{t}.{i}") for i in range(7)])
    ancilla_ids = [f"{t}.z.{i}" for i in range(3)]
    a = tuple([QubitId(i) for i in ancilla_ids])

    x_syndrome_extraction = (
        [cliffords.H(a) for a in a]
        + [
            cliffords.CX(a[0], target[0]),
            cliffords.CX(a[0], target[1]),
            cliffords.CX(a[0], target[3]),
            cliffords.CX(a[0], target[4]),
            cliffords.CX(a[1], target[0]),
            cliffords.CX(a[1], target[2]),
            cliffords.CX(a[1], target[3]),
            cliffords.CX(a[1], target[5]),
            cliffords.CX(a[2], target[1]),
            cliffords.CX(a[2], target[2]),
            cliffords.CX(a[2], target[3]),
            cliffords.CX(a[2], target[6]),
        ]
        + [cliffords.H(a) for a in a]
    )

    return Kernel.allocate(*ancilla_ids, instructions=x_syndrome_extraction, callback=Correct_X(qubit=t))


def z_syndrome_extraction(t: QubitId):
    target = tuple([QubitId(f"{t}.{i}") for i in range(7)])
    ancilla_ids = [f"{t}.z.{i}" for i in range(3)]
    a = tuple([QubitId(i) for i in ancilla_ids])

    z_syndrome_extraction = [
        cliffords.CX(target[0], a[0]),
        cliffords.CX(target[1], a[0]),
        cliffords.CX(target[3], a[0]),
        cliffords.CX(target[4], a[0]),
        cliffords.CX(target[0], a[1]),
        cliffords.CX(target[2], a[1]),
        cliffords.CX(target[3], a[1]),
        cliffords.CX(target[5], a[1]),
        cliffords.CX(target[1], a[2]),
        cliffords.CX(target[2], a[2]),
        cliffords.CX(target[3], a[2]),
        cliffords.CX(target[6], a[2]),
    ]

    return Kernel.allocate(*ancilla_ids, instructions=z_syndrome_extraction, callback=Correct_Z(qubit=t))


# These maps are derived from the classical Hamming syndrome decoding
syndrome_table = {
    (0, 0, 0): None,
    (0, 0, 1): 6,
    (0, 1, 0): 5,
    (0, 1, 1): 3,
    (1, 0, 0): 4,
    (1, 0, 1): 2,
    (1, 1, 0): 1,
    (1, 1, 1): 0,
}


def correct_x(context: ClassicContext, *, qubit: QubitId):
    syndrome = (context.consume(), context.consume(), context.consume())
    fault = syndrome_table.get(syndrome)

    if fault is not None:
        target = tuple([QubitId(f"{qubit}.{i}") for i in range(7)])
        return Kernel(target=None, instructions=[cliffords.X(target[fault])])


def correct_z(context: ClassicContext, *, qubit: QubitId):
    syndrome = (context.consume(), context.consume(), context.consume())
    fault = syndrome_table.get(syndrome)

    if fault is not None:
        target = tuple([QubitId(f"{qubit}.{i}") for i in range(7)])
        return Kernel(target=None, instructions=[cliffords.Z(target[fault])])


def decode(context: ClassicContext):
    outcome = np.array([context.consume() for _ in range(7)])
    check1 = int(np.dot(outcome, np.array([1, 1, 0, 1, 1, 0, 0])) % 2)
    check2 = int(np.dot(outcome, np.array([1, 0, 1, 1, 0, 1, 0])) % 2)
    check3 = int(np.dot(outcome, np.array([0, 1, 1, 1, 0, 0, 1])) % 2)
    syndrome = (check1, check2, check3)
    fault = syndrome_table.get(syndrome)
    logger.debug(f"outcome: {outcome}, syndrome: {syndrome}, correction: {fault}")

    if fault is not None:
        outcome[fault] = (outcome[fault] + 1) % 2

    context.collect(int(np.sum(outcome) % 2))


Correct_X = ClassicDefinition.from_callback(correct_x)
Correct_Z = ClassicDefinition.from_callback(correct_z)

Decode = ClassicDefinition.from_callback(decode)


class SteaneCompiler(Compiler):
    def __init__(self):
        super().__init__(
            name="steane",
            source=cliffords.instruction_set,
            target=cliffords.instruction_set,
            handlers={
                cliffords.X.name: handle_x,
                cliffords.Z.name: handle_z,
                cliffords.H.name: handle_h,
                cliffords.CX.name: handle_cx,
            },
            compiler_callbacks={Correct_X, Correct_Z, Decode},
        )

    def compile_kernel(self, kernel: Kernel):
        # Build list: prepare_zero + instructions
        instructions = []
        if kernel.target:
            instructions.append(handle_prepare_zero(kernel.target))

        if len(kernel.instructions) > 0:
            if kernel.target:
                instructions.extend(
                    [
                        z_syndrome_extraction(kernel.target),
                        x_syndrome_extraction(kernel.target),
                    ]
                )

            for i, inst in enumerate(kernel.instructions):
                is_last = i == len(kernel.instructions) - 1

                if isinstance(inst, Kernel):
                    instructions.append(self.compile_kernel(inst))
                else:
                    instructions.append(self.handlers[inst.name](inst))
                    if not is_last:
                        for t in inst.targets:
                            instructions.extend(
                                [
                                    z_syndrome_extraction(t),
                                    x_syndrome_extraction(t),
                                ]
                            )

        # Create the result kernel
        if kernel.target:
            # Use Kernel.allocate to create nested structure for 7 physical qubits
            qubits = [f"{kernel.target}.{i}" for i in range(7)]

            # Create the nested kernel structure with Decode callback on the innermost level
            innermost_kernel = Kernel.allocate(*qubits, instructions=instructions, callback=Decode())

            # Attach final callback if needed
            final_callback = self.compile_callback(kernel.callback)
            if final_callback:
                return Kernel(target=None, instructions=[innermost_kernel], callback=final_callback)
            else:
                return innermost_kernel
        else:
            # No targets, just return kernel with instructions and callback
            final_callback = self.compile_callback(kernel.callback)
            return Kernel(target=None, instructions=instructions, callback=final_callback)
