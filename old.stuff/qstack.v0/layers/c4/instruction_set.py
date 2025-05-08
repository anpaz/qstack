from qcir import QubitId, RegisterId
from qstack.gadget_definition import GadgetDefinition

PrepareZeroZero = GadgetDefinition(name="|00⟩", targets=(QubitId,))

PreparePlusPlus = GadgetDefinition(name="|++⟩", targets=(QubitId,))

XI = GadgetDefinition(name="xi", targets=(QubitId,))

IX = GadgetDefinition(name="ix", targets=(QubitId,))

ZI = GadgetDefinition(name="zi", targets=(QubitId,))

IZ = GadgetDefinition(name="iz", targets=(QubitId,))

HH = GadgetDefinition(name="hh", targets=(QubitId,))

CX_01 = GadgetDefinition(name="cx_01", targets=(QubitId, QubitId))

CX_10 = GadgetDefinition(name="cx_10", targets=(QubitId, QubitId))

CX_11 = GadgetDefinition(name="cx", targets=(QubitId, QubitId))

MeasureZZ = GadgetDefinition(name="⟨zz|", targets=(QubitId, RegisterId))

MeasureXX = GadgetDefinition(name="⟨xx|", targets=(QubitId, RegisterId))
