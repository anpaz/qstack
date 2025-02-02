import math

from ..layer import Layer, QuantumDefinition, ClassicDefinition, Outcome, Matrix
from ..ast import ParameterValue


def vote(m1: Outcome, m2: Outcome, m3: Outcome) -> Outcome:
    print("on vote", m1, m2, m3)
    if m1 + m2 + m3 >= 2:
        return 1
    else:
        return 0


def skew(p: float) -> Matrix:
    theta = 2 * math.asin(math.sqrt(p))
    c = math.cos(theta / 2)
    s = math.sin(theta / 2)
    return [[c, -1j * s], [-1j * s, c]]


## Classic Instructions
Vote = ClassicDefinition.from_callback(vote)


## Quantum Instructions
Flip = QuantumDefinition.from_matrix(name="flip", targets=1, matrix=[[0, 1], [1, 0]])

Mix = QuantumDefinition.from_matrix(name="mix", targets=1, matrix=[[0.7071, 0.7071], [0.7071, -0.7071]])

Skew = QuantumDefinition.with_parameters(name="skew", targets=1, factory=skew)

Entangle = QuantumDefinition.from_matrix(
    name="entangle", targets=2, matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]
)

layer = Layer(name="toy", quantum_definitions=set([Flip, Mix, Skew, Entangle]), classic_definitions=set([Vote]))
