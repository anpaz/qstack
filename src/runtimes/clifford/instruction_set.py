from qcir import QubitId, RegisterId
from qstack.instruction_definition import InstructionDefinition

Measure = InstructionDefinition(name="measure", targets=[QubitId, RegisterId], aliases=["mz"])

PrepareZero = InstructionDefinition(name="|0⟩", targets=[QubitId], aliases=["|0>", "|+z⟩", "|+z>"])

H = InstructionDefinition(name="h", targets=[QubitId])

X = InstructionDefinition(name="x", parameters=[float], targets=[QubitId])

Y = InstructionDefinition(name="y", targets=[QubitId])

Z = InstructionDefinition(name="z", targets=[QubitId])

CX = InstructionDefinition(name="cx", targets=[QubitId, QubitId], aliases=["cnot"])

CY = InstructionDefinition(name="cy", targets=[QubitId, QubitId])

CZ = InstructionDefinition(name="cz", targets=[QubitId, QubitId])

S = InstructionDefinition(name="s", targets=[QubitId], aliases=["sz"])

SAdj = InstructionDefinition(name="s_adj", targets=[QubitId], aliases=["sz_adj"])

SX = InstructionDefinition(name="sx", targets=[QubitId])

SXAdj = InstructionDefinition(name="sx_adj", targets=[QubitId])

SY = InstructionDefinition(name="sy", targets=[QubitId])

SYAdj = InstructionDefinition(name="sy_adj", targets=[QubitId])
