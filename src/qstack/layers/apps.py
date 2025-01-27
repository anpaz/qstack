from ..layer import Layer, InstructionDefinition, ContinuationDefinition
from ..ast import Outcome, Kernel

Mix = InstructionDefinition(name="mix", targets=["q1"], matrix=[[0.7071, 0.7071], [0.7071, -0.7071]])

Entangle = InstructionDefinition(
    name="entangle", targets=["q1", "q2"], matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]
)


def _fix(m0: Outcome, m1: Outcome) -> Kernel:
    return None


Fix = ContinuationDefinition(
    name="fix",
    callback=_fix,
)

layer = Layer(name="Apps", instructions=set([Mix, Entangle]))
