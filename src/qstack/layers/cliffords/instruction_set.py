from qcir import QubitId, RegisterId
from qstack.gadget_definition import GadgetDefinition

PrepareZero = GadgetDefinition(name="|0⟩", targets=[QubitId], aliases=["|0>", "|+z⟩", "|+z>"])

MeasureZ = GadgetDefinition(name="⟨z|", targets=[RegisterId, QubitId], aliases=["mz", "⟨+z|", "measure"])

S = GadgetDefinition(name="s", targets=[QubitId])

SAdj = GadgetDefinition(name="s_adj", targets=[QubitId])

H = GadgetDefinition(name="h", targets=[QubitId])

CX = GadgetDefinition(name="cx", targets=[QubitId, QubitId], aliases=["cnot"])
