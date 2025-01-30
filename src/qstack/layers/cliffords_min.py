from ..layer import Layer, QuantumInstructionDefinition


X = QuantumInstructionDefinition(name="x", targets=["q1"], matrix=[[0, 1], [1, 0]])

Y = QuantumInstructionDefinition(name="y", targets=["q1"], matrix=[[0, -1j], [1j, 0]])

Z = QuantumInstructionDefinition(name="z", targets=["q1"], matrix=[[1, 0], [0, -1]])

H = QuantumInstructionDefinition(name="h", targets=["q1"], matrix=[[0.7071, 0.7071], [0.7071, -0.7071]])

CX = QuantumInstructionDefinition(
    name="cx", targets=["q1", "q2"], matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]
)

CZ = QuantumInstructionDefinition(
    name="cz", targets=["q1", "q2"], matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, -1]]
)

layer = Layer(name="cliffords-min", quantum_instructions=set([X, Y, Z, H, CX, CZ]), classic_instructions=set())
