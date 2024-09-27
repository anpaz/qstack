from qcir import QubitId, RegisterId
from qstack.instruction_definition import InstructionDefinition

from runtimes.clifford.instruction_set import PrepareZero, H, MeasureZ, CX, MeasurePauli, ApplyPauli

# Supported Clifford operations:
# MeasureZ = MeasureZ
# PrepareZero = PrepareZero
Hadamard = H
CtrlX = CX
# MeasurePauli = MeasurePauli

# Other instructions
PrepareBell = InstructionDefinition(name="|bell⟩", targets=(QubitId, QubitId))
