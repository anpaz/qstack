from qcir import QubitId, RegisterId
from qstack import InstructionDefinition

v_type = complex | float | int

# fmt: off
Matrix1 = InstructionDefinition(
    name="matrix1",
    parameters=[
        v_type, v_type,
        v_type, v_type,
    ],
    targets=[QubitId],
)

Matrix2 = InstructionDefinition(
    name="matrix2",
    parameters=[
        v_type, v_type, v_type, v_type,
        v_type, v_type, v_type, v_type,
        v_type, v_type, v_type, v_type,
        v_type, v_type, v_type, v_type,
    ],
    targets=[QubitId, QubitId]
)

Measure = InstructionDefinition(
    name="measure",
    targets=[QubitId, RegisterId]
)
# fmt: on
