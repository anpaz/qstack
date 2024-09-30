from qcir import QubitId, RegisterId
from qstack.instruction_definition import InstructionDefinition

PrepareZeroZero = InstructionDefinition(name="|00⟩", targets=(QubitId,))

PreparePlusPlus = InstructionDefinition(name="|++⟩", targets=(QubitId,))

XI = InstructionDefinition(name="xi", targets=(QubitId,))

IX = InstructionDefinition(name="ix", targets=(QubitId,))

ZI = InstructionDefinition(name="zi", targets=(QubitId,))

IZ = InstructionDefinition(name="iz", targets=(QubitId,))

HH = InstructionDefinition(name="hh", targets=(QubitId,))

CX_01 = InstructionDefinition(name="cx_01", targets=(QubitId, QubitId))

CX_10 = InstructionDefinition(name="cx_10", targets=(QubitId, QubitId))

CX_11 = InstructionDefinition(name="cx", targets=(QubitId, QubitId))

MeasureZZ = InstructionDefinition(name="⟨zz|", targets=(QubitId, RegisterId))

MeasureXX = InstructionDefinition(name="⟨xx|", targets=(QubitId, RegisterId))
