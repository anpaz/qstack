from qcir import QubitId, RegisterId
from qstack.gadget_definition import GadgetDefinition

Measure = GadgetDefinition(name="measure", targets=[QubitId, RegisterId])

PrepareZero = GadgetDefinition(name="|0⟩", targets=[QubitId])

U1 = GadgetDefinition(name="u1", parameters=[float, float], targets=[QubitId])

RZ = GadgetDefinition(name="rz", parameters=[float], targets=[QubitId])

RZZ = GadgetDefinition(name="rzz", parameters=[float], targets=[QubitId, QubitId])

ZZ = GadgetDefinition(name="zz", targets=[QubitId, QubitId])
