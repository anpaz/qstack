from qcir import QubitId, RegisterId
from qstack.instruction_definition import InstructionDefinition

PrepareZero = InstructionDefinition(name="|0⟩", targets=[QubitId], aliases=["|0>", "|+z⟩", "|+z>"])

MeasureZ = InstructionDefinition(name="⟨z|", targets=[RegisterId, QubitId], aliases=["mz", "⟨+z|", "measure"])

S = InstructionDefinition(name="s", targets=[QubitId])

SAdj = InstructionDefinition(name="s_adj", targets=[QubitId])

H = InstructionDefinition(name="h", targets=[QubitId])

CX = InstructionDefinition(name="cx", targets=[QubitId, QubitId], aliases=["cnot"])
