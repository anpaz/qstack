from ..layer import Layer, QuantumInstructionDefinition, ClassicInstructionDefinition
from ..ast import Outcome, Kernel, QubitId


def fix(m0: Outcome, m1: Outcome, *, q: QubitId) -> Kernel:
    if m0 == m1:
        return Kernel(
            targets=[],
            instructions=[
                Flip(q),
            ],
        )


Flip = QuantumInstructionDefinition(name="flip", targets=["q1"], matrix=[[0, 1], [1, 0]])

Mix = QuantumInstructionDefinition(name="mix", targets=["q1"], matrix=[[0.7071, 0.7071], [0.7071, -0.7071]])

Entangle = QuantumInstructionDefinition(
    name="entangle", targets=["q1", "q2"], matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]
)

Fix = ClassicInstructionDefinition.from_callback(fix)

layer = Layer(name="Apps", quantum_instructions=set([Flip, Mix, Entangle]), classic_instructions=set([Fix]))
