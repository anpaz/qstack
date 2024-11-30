from qcir import QubitId, RegisterId
from qstack.gadget_definition import GadgetDefinition

from qstack.paulis import Pauli

from qstack.layers.cliffords.instruction_set import MeasureZ, PrepareZero, H, CX, S, SAdj

MeasureZ = MeasureZ

PrepareZero = PrepareZero

H = H

S = S

SAdj = SAdj

X = GadgetDefinition(name="x", parameters=[float], targets=[QubitId])

Y = GadgetDefinition(name="y", targets=[QubitId])

Z = GadgetDefinition(name="z", targets=[QubitId])

CX = GadgetDefinition(name="cx", targets=[QubitId, QubitId], aliases=["cnot"])

CY = GadgetDefinition(name="cy", targets=[QubitId, QubitId])

CZ = GadgetDefinition(name="cz", targets=[QubitId, QubitId])

SX = GadgetDefinition(name="sx", targets=[QubitId])

SXAdj = GadgetDefinition(name="sx_adj", targets=[QubitId])

SY = GadgetDefinition(name="sy", targets=[QubitId])

SYAdj = GadgetDefinition(name="sy_adj", targets=[QubitId])

ApplyPauli = GadgetDefinition(name="pauli", targets=[QubitId, ...], parameters=[Pauli, ...])

MeasurePauli = GadgetDefinition(name="mpp", targets=[RegisterId, QubitId, ...], parameters=[Pauli, ...])
