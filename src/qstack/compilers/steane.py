import logging
import numpy as np
from dataclasses import replace

from ..compiler import Compiler
from ..ast import QuantumInstruction, Kernel, QubitId
from ..layers import cliffords_min as cliffords
from ..layer import ClassicDefinition
from ..processors import Outcome
from ..stack import LayerNode

logger = logging.getLogger("qstack")

## Stabilizers we're using:
#    [1, 1, 0, 1, 1, 0, 0],
#    [1, 0, 1, 1, 0, 1, 0],
#    [0, 1, 1, 1, 0, 0, 1],


def handle_x(inst: QuantumInstruction):
    target = tuple([QubitId(f"{inst.targets[0]}.{i}") for i in range(7)])
    return Kernel(targets=[], instructions=[cliffords.X(q) for q in target])


def handle_z(inst: QuantumInstruction):
    target = tuple([QubitId(f"{inst.targets[0]}.{i}") for i in range(7)])
    return Kernel(targets=[], instructions=[cliffords.Z(q) for q in target])


def handle_h(inst: QuantumInstruction):
    target = tuple([QubitId(f"{inst.targets[0]}.{i}") for i in range(7)])
    return Kernel(targets=[], instructions=[cliffords.H(q) for q in target])


def handle_cx(inst: QuantumInstruction):
    ctrl = tuple([QubitId(f"{inst.targets[0]}.{i}") for i in range(7)])
    target = tuple([QubitId(f"{inst.targets[1]}.{i}") for i in range(7)])

    return Kernel(targets=[], instructions=[cliffords.CX(c, t) for (c, t) in zip(ctrl, target)])


def handle_prepare_zero(t: QubitId):
    q = tuple([QubitId(f"{t}.{i}") for i in range(7)])
    a = QubitId(f"{t}.a")

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

    return Kernel(targets=[], instructions=instructions)


def x_syndrome_extraction(t: QubitId):
    target = tuple([QubitId(f"{t}.{i}") for i in range(7)])
    a = tuple([QubitId(f"{t}.x.{i}") for i in range(3)])

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

    return Kernel(targets=a, instructions=x_syndrome_extraction, callback=Correct_X(qubit=t))


def z_syndrome_extraction(t: QubitId):
    target = tuple([QubitId(f"{t}.{i}") for i in range(7)])
    a = tuple([QubitId(f"{t}.z.{i}") for i in range(3)])

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

    return Kernel(targets=a, instructions=z_syndrome_extraction, callback=Correct_Z(qubit=t))


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


def correct_x(m0: Outcome, m1: Outcome, m2: Outcome, *, qubit: QubitId):
    syndrome = (m0, m1, m2)
    fault = syndrome_table.get(syndrome)

    if fault is not None:
        target = tuple([QubitId(f"{qubit}.{i}") for i in range(7)])
        return Kernel(targets=[], instructions=[cliffords.X(QubitId(f"{qubit}.{target[fault]}"))])
    else:
        return None


def correct_z(m0: Outcome, m1: Outcome, m2: Outcome, *, qubit: QubitId):
    syndrome = (m0, m1, m2)
    fault = syndrome_table.get(syndrome)

    if fault is not None:
        target = tuple([QubitId(f"{qubit}.{i}") for i in range(7)])
        return Kernel(targets=[], instructions=[cliffords.Z(QubitId(f"{qubit}.{target[fault]}"))])
    else:
        return None


def decode(m0: Outcome, m1: Outcome, m2: Outcome, m3: Outcome, m4: Outcome, m5: Outcome, m6: Outcome):
    outcome = np.array([m0, m1, m2, m3, m4, m5, m6])
    check1 = int(np.dot(outcome, np.array([1, 1, 0, 1, 1, 0, 0])) % 2)
    check2 = int(np.dot(outcome, np.array([1, 0, 1, 1, 0, 1, 0])) % 2)
    check3 = int(np.dot(outcome, np.array([0, 1, 1, 1, 0, 0, 1])) % 2)
    syndrome = (check1, check2, check3)
    fault = syndrome_table.get(syndrome)
    logger.debug(f"outcome: {outcome}, syndrome: {syndrome}, correction: {fault}")

    if fault is not None:
        outcome[fault] = (outcome[fault] + 1) % 2

    return int(np.sum(outcome) % 2)


Correct_X = ClassicDefinition.from_callback(correct_x)
Correct_Z = ClassicDefinition.from_callback(correct_z)

Decode = ClassicDefinition.from_callback(decode)


class SteaneCompiler(Compiler):
    def __init__(self):
        super().__init__(
            name="steane",
            source=cliffords.layer,
            target=cliffords.layer.extend_with(classic={Correct_X, Correct_Z, Decode}),
            handlers={
                cliffords.X.name: handle_x,
                cliffords.Z.name: handle_z,
                cliffords.H.name: handle_h,
                cliffords.CX.name: handle_cx,
            },
        )

    def eval(self, kernel: Kernel, node: LayerNode):
        def rename_callback(cb):
            if cb is None:
                return None
            if ":" not in cb.name:
                return replace(cb, name=f"{node.namespace}{cb.name}")
            return cb

        def build_innermost_kernel():
            # Build list: prepare_zero + instructions
            instructions = [handle_prepare_zero(t) for t in kernel.targets]

            if len(kernel.instructions) > 0:
                for t in kernel.targets:
                    instructions.extend(
                        [
                            z_syndrome_extraction(t),
                            x_syndrome_extraction(t),
                        ]
                    )

                for i, inst in enumerate(kernel.instructions):
                    is_last = i == len(kernel.instructions) - 1

                    if isinstance(inst, Kernel):
                        instructions.append(self.eval(inst, node))
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

            return Kernel(targets=[], instructions=instructions)

        # Build the full nested structure from inside out
        current_kernel = build_innermost_kernel()

        for t in reversed(kernel.targets):
            qubits = tuple(QubitId(f"{t}.{i}") for i in range(7))
            current_kernel = Kernel(targets=qubits, instructions=[current_kernel], callback=Decode())
            # current_kernel = Kernel(targets=qubits, instructions=[current_kernel])

        # Attach final callback if needed
        final_callback = rename_callback(kernel.callback)
        if final_callback:
            return Kernel(targets="", instructions=[current_kernel], callback=final_callback)
        else:
            return current_kernel
