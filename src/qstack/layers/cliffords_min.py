from ..layer import Layer, QuantumDefinition


X = QuantumDefinition(name="x", targets=["q1"], matrix=[[0, 1], [1, 0]])

Y = QuantumDefinition(name="y", targets=["q1"], matrix=[[0, -1j], [1j, 0]])

Z = QuantumDefinition(name="z", targets=["q1"], matrix=[[1, 0], [0, -1]])

H = QuantumDefinition(name="h", targets=["q1"], matrix=[[0.7071, 0.7071], [0.7071, -0.7071]])

CX = QuantumDefinition(
    name="cx", targets=["q1", "q2"], matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]
)

CZ = QuantumDefinition(
    name="cz", targets=["q1", "q2"], matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, -1]]
)

layer = Layer(name="cliffords-min", quantum_definitions=set([X, Y, Z, H, CX, CZ]), classic_definitions=set())
