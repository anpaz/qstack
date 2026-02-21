from ..instruction_set import InstructionSet, QuantumDefinition, Matrix
import cmath


## Quantum Instructions
def u1(theta: float, phi: float) -> Matrix:
    i = 1j
    a_00 = cmath.cos(theta / 2)
    a_11 = cmath.cos(theta / 2)

    #  −𝑖 𝑒^{−𝑖𝜑} sin(𝜃/2)
    exponent = cmath.exp(-i * phi)
    sine_value = cmath.sin(theta / 2)
    a_01 = -i * exponent * sine_value

    #  −𝑖 𝑒^{𝑖𝜑} sin(𝜃/2)
    exponent = cmath.exp(i * phi)
    sine_value = cmath.sin(theta / 2)
    a_10 = -i * exponent * sine_value

    # fmt: off
    return [
        [a_00, a_01],
        [a_10, a_11],
    ]


def rz(theta: float) -> Matrix:
    i = 1j
    a_00 = cmath.exp(-i * theta / 2.0)
    a_11 = cmath.exp(i * theta / 2.0)
    # fmt: off
    return [
        [a_00, 0.0],
        [0.0, a_11],
    ]


def rzz(theta: float) -> Matrix:
    i = 1j
    const = cmath.exp(-i * theta / 2.0)
    a = cmath.exp(i * theta)
    # fmt: off
    return [
        [const,     0.0,      0.0,   0.0],
        [  0.0, a*const,      0.0,   0.0],
        [  0.0,     0.0,  a*const,   0.0],
        [  0.0,     0.0,      0.0, const],
    ]


def zz() -> Matrix:
    i = 1j
    const = cmath.exp(-i * cmath.pi / 4.0)
    # fmt: off
    return [
        [const,       0,       0,     0],
        [    0, i*const,       0,     0],
        [    0,       0, i*const,     0],
        [    0,       0,       0, const],
    ]


U1 = QuantumDefinition.with_parameters(name="u1", targets=1, factory=u1)

RZ = QuantumDefinition.with_parameters(name="rz", targets=1, factory=rz)

RZZ = QuantumDefinition.with_parameters(name="rzz", targets=2, factory=rzz)

ZZ = QuantumDefinition.from_matrix(name="zz", targets=2, matrix=zz())

instruction_set = InstructionSet(name="h2", quantum_definitions=set([U1, RZ, RZZ, ZZ]))
