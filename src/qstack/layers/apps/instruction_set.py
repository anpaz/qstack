from qcir import QubitId, RegisterId
from qstack.instruction_definition import InstructionDefinition

PrepareZero = InstructionDefinition(name="|0⟩", targets=[QubitId])

PrepareOne = InstructionDefinition(name="|1⟩", targets=[QubitId])

PrepareRandom = InstructionDefinition(name="|random⟩", targets=[QubitId])

PrepareBell = InstructionDefinition(name="|bell⟩", targets=(QubitId, QubitId))

Measure = InstructionDefinition(name="measure", targets=(RegisterId, QubitId))
