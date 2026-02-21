import math
from ..compiler import Compiler
from ..ast import QuantumInstruction, Kernel
from ..instruction_sets import cliffords_min as cliffords
from ..instruction_sets import h2


# U1(theta, phi) matrix:
#   [[cos(theta/2),                    -i*exp(-i*phi)*sin(theta/2)],
#    [-i*exp(i*phi)*sin(theta/2),      cos(theta/2)]]
#
# Decompositions (up to global phase):
#   X = U1(pi, 0)
#   Y = U1(pi, pi/2)
#   Z = RZ(pi)
#   H = RZ(pi) * U1(pi/2, -pi/2)
#
# For two-qubit gates, CZ can be decomposed using ZZ and single-qubit rotations:
#   CZ = (I ⊗ RZ(-pi/2)) * (RZ(-pi/2) ⊗ I) * ZZ
#   CX = (I ⊗ H) * CZ * (I ⊗ H)


def handle_x(inst: QuantumInstruction):
    """X gate: U1(pi, 0)"""
    return h2.U1(inst.targets[0], theta=math.pi, phi=0)


def handle_y(inst: QuantumInstruction):
    """Y gate: U1(pi, pi/2)"""
    return h2.U1(inst.targets[0], theta=math.pi, phi=math.pi / 2)


def handle_z(inst: QuantumInstruction):
    """Z gate: RZ(pi)"""
    return h2.RZ(inst.targets[0], theta=math.pi)


def handle_h(inst: QuantumInstruction):
    """H gate: RZ(pi) * U1(pi/2, -pi/2)"""
    target = inst.targets[0]
    return Kernel(
        target=None,
        instructions=[
            h2.U1(target, theta=math.pi / 2, phi=-math.pi / 2),
            h2.RZ(target, theta=math.pi),
        ],
    )


def handle_cz(inst: QuantumInstruction):
    """CZ gate: (I ⊗ RZ(-pi/2)) * (RZ(-pi/2) ⊗ I) * ZZ"""
    q0, q1 = inst.targets
    return Kernel(
        target=None,
        instructions=[
            h2.ZZ(q0, q1),
            h2.RZ(q0, theta=-math.pi / 2),
            h2.RZ(q1, theta=-math.pi / 2),
        ],
    )


def handle_cx(inst: QuantumInstruction):
    """CX gate: (I ⊗ H) * CZ * (I ⊗ H) = H on target, then CZ, then H on target"""
    control, target = inst.targets
    return Kernel(
        target=None,
        instructions=[
            # H on target
            h2.U1(target, theta=math.pi / 2, phi=-math.pi / 2),
            h2.RZ(target, theta=math.pi),
            # CZ
            h2.ZZ(control, target),
            h2.RZ(control, theta=-math.pi / 2),
            h2.RZ(target, theta=-math.pi / 2),
            # H on target
            h2.U1(target, theta=math.pi / 2, phi=-math.pi / 2),
            h2.RZ(target, theta=math.pi),
        ],
    )


class CliffordsToH2Compiler(Compiler):
    def __init__(self):
        super().__init__(
            name="cliffords2h2",
            source=cliffords.instruction_set,
            target=h2.instruction_set,
            handlers={
                cliffords.X.name: handle_x,
                cliffords.Y.name: handle_y,
                cliffords.Z.name: handle_z,
                cliffords.H.name: handle_h,
                cliffords.CX.name: handle_cx,
                cliffords.CZ.name: handle_cz,
            },
        )
