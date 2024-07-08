from qcir import QubitId, RegisterId
from qstack.instruction_definition import InstructionDefinition

Measure = InstructionDefinition(name="measure", targets=[QubitId, RegisterId])

PrepareZero = InstructionDefinition(name="|0⟩", targets=[QubitId])

U1 = InstructionDefinition(name="u1", parameters=[float, float], targets=[QubitId])

RZ = InstructionDefinition(name="rz", parameters=[float], targets=[QubitId])

RZZ = InstructionDefinition(name="rzz", parameters=[float], targets=[QubitId, QubitId])

ZZ = InstructionDefinition(name="zz", targets=[QubitId, QubitId])
