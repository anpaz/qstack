from qcir import QubitId, RegisterId
from qstack import InstructionDefinition

# fmt: off
Matrix1 = InstructionDefinition(
    name="matrix1",
    parameters=[
        float, float,
        float, float,
    ],
    targets=[QubitId],
)

Matrix2 = InstructionDefinition(
    name="matrix2",
    parameters=[
        float, float, float, float,
        float, float, float, float,
        float, float, float, float,
        float, float, float, float,
    ],
    targets=[QubitId, QubitId]
)

Measure = InstructionDefinition(
    name="measure",
    targets=[QubitId, RegisterId]
)
# fmt: on
