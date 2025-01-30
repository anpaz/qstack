from qcir import QubitId, RegisterId
from qstack import GadgetDefinition

v_type = complex | float | int

# fmt: off
Matrix1 = GadgetDefinition(
    name="matrix1",
    parameters=(
        v_type, v_type,
        v_type, v_type,
    ),
    targets=(QubitId,),
 )

Matrix2 = GadgetDefinition(
    name="matrix2",
    parameters=(
        v_type, v_type, v_type, v_type,
        v_type, v_type, v_type, v_type,
        v_type, v_type, v_type, v_type,
        v_type, v_type, v_type, v_type,
    ),
    targets=(QubitId, QubitId)
)

Measure = GadgetDefinition(
    name="measure",
    targets=(RegisterId, QubitId)
)
# fmt: on
