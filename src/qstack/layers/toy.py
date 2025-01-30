from ..layer import Layer, QuantumInstructionDefinition, ClassicInstructionDefinition, Outcome


def vote(m1: Outcome, m2: Outcome, m3: Outcome) -> Outcome:
    print("on vote", m1, m2, m3)
    if m1 + m2 + m3 >= 2:
        return 1
    else:
        return 0


## Classic Instructions
Vote = ClassicInstructionDefinition.from_callback(vote)

## Quantum Instructions
Flip = QuantumInstructionDefinition(name="flip", targets=["q1"], matrix=[[0, 1], [1, 0]])

Mix = QuantumInstructionDefinition(name="mix", targets=["q1"], matrix=[[0.7071, 0.7071], [0.7071, -0.7071]])

Entangle = QuantumInstructionDefinition(
    name="entangle", targets=["q1", "q2"], matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]
)

layer = Layer(name="toy", quantum_instructions=set([Flip, Mix, Entangle]), classic_instructions=set([Vote]))
