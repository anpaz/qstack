from qcir import QubitId, RegisterId
from qstack.gadget_definition import GadgetDefinition

PrepareZero = GadgetDefinition(name="|0⟩", targets=[QubitId])

PrepareOne = GadgetDefinition(name="|1⟩", targets=[QubitId])

PrepareRandom = GadgetDefinition(name="|random⟩", targets=[QubitId])

PrepareBell = GadgetDefinition(name="|bell⟩", targets=(QubitId, QubitId))
