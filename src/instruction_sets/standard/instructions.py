from qcir import QubitId, RegisterId
from qstack.instruction_definition import InstructionDefinition

# fmt: off
PrepareZero = InstructionDefinition(
    name="|0⟩",
    targets=[QubitId]
)

Hadamard = InstructionDefinition(
    name="H",
    targets=[QubitId]
)

CtrlX = InstructionDefinition(
    name="CX",
    targets=[QubitId, QubitId]
)

PrepareBell = InstructionDefinition(
    name="|bell⟩",
    targets=[QubitId, QubitId]
)

MeasureZ = InstructionDefinition(
    name="mz",
    targets=[QubitId, RegisterId]
)
# fmt: on
