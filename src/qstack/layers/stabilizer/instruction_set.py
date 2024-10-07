from qcir import QubitId, RegisterId
from qstack.instruction_definition import InstructionDefinition

from qstack.paulis import Pauli

from qstack.layers.cliffords.instruction_set import MeasureZ, PrepareZero, H, CX, S, SAdj

MeasureZ = MeasureZ

PrepareZero = PrepareZero

H = H

S = S

SAdj = SAdj

X = InstructionDefinition(name="x", parameters=[float], targets=[QubitId])

Y = InstructionDefinition(name="y", targets=[QubitId])

Z = InstructionDefinition(name="z", targets=[QubitId])

CX = InstructionDefinition(name="cx", targets=[QubitId, QubitId], aliases=["cnot"])

CY = InstructionDefinition(name="cy", targets=[QubitId, QubitId])

CZ = InstructionDefinition(name="cz", targets=[QubitId, QubitId])

SX = InstructionDefinition(name="sx", targets=[QubitId])

SXAdj = InstructionDefinition(name="sx_adj", targets=[QubitId])

SY = InstructionDefinition(name="sy", targets=[QubitId])

SYAdj = InstructionDefinition(name="sy_adj", targets=[QubitId])

ApplyPauli = InstructionDefinition(name="pauli", targets=[QubitId, ...], parameters=[Pauli, ...])

MeasurePauli = InstructionDefinition(name="mpp", targets=[RegisterId, QubitId, ...], parameters=[Pauli, ...])
