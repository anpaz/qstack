from qcir import QubitId, RegisterId
from qstack.instruction_definition import InstructionDefinition

# fmt: off
PrepareBell = InstructionDefinition(
    name="|bell⟩",
    targets=[QubitId, QubitId]
)

MeasureZ = InstructionDefinition(
    name="mz",
    targets=[QubitId, RegisterId]
)
# fmt: on
