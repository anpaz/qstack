import math

from ..instruction_set import InstructionSet, QuantumDefinition, Matrix
from ..classic_processor import ClassicalContext


## Quantum Instructions
def skew(bias: float) -> Matrix:
    theta = 2 * math.asin(math.sqrt(float(bias)))
    c = math.cos(theta / 2)
    s = math.sin(theta / 2)
    return [[c, -1j * s], [-1j * s, c]]


Flip = QuantumDefinition.from_matrix(name="flip", targets=1, matrix=[[0, 1], [1, 0]])

Mix = QuantumDefinition.from_matrix(name="mix", targets=1, matrix=[[0.7071, 0.7071], [0.7071, -0.7071]])

Skew = QuantumDefinition.with_parameters(name="skew", targets=1, factory=skew)

Entangle = QuantumDefinition.from_matrix(
    name="entangle", targets=2, matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]
)


## Classic Instructions
def vote(context: ClassicalContext):
    m1 = context.consume()
    m2 = context.consume()
    m3 = context.consume()
    print("on vote", m1, m2, m3)
    if m1 + m2 + m3 >= 2:
        context.collect(1)
    else:
        context.collect(0)

    return None


instruction_set = InstructionSet(name="toy", quantum_definitions=set([Flip, Mix, Skew, Entangle]))
