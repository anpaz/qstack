from ..layer import Layer, QuantumDefinition


X = QuantumDefinition.from_matrix(name="x", targets=1, matrix=[[0, 1], [1, 0]])

Y = QuantumDefinition.from_matrix(name="y", targets=1, matrix=[[0, -1j], [1j, 0]])

Z = QuantumDefinition.from_matrix(name="z", targets=1, matrix=[[1, 0], [0, -1]])

H = QuantumDefinition.from_matrix(name="h", targets=1, matrix=[[0.7071, 0.7071], [0.7071, -0.7071]])

CX = QuantumDefinition.from_matrix(
    name="cx", targets=2, matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]
)

CZ = QuantumDefinition.from_matrix(
    name="cz", targets=["q1", "q2"], matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, -1]]
)

layer = Layer(name="cliffords-min", quantum_definitions=set([X, Y, Z, H, CX, CZ]), classic_definitions=set())
