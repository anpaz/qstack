"""Fresh-construction lowerings and optimizations for qstack modules."""

from qstack.passes.base import (
    Encoding,
    LoweringContext,
    LoweringPass,
    OptimizationPass,
    PASS_HISTORY_ATTR,
    PassError,
    QubitGroup,
    Replacement,
)
from qstack.passes.clifford_peephole import (
    CliffordPeepholeOptimization,
    optimize_cliffords,
)
from qstack.passes.cliffords2atoms import (
    CliffordsToAtomsLowering,
    lower_cliffords_to_atoms,
)
from qstack.passes.cliffords2h2 import CliffordsToH2Lowering, lower_cliffords_to_h2
from qstack.passes.rep3_bit import (
    Rep3BitLowering,
    lower_rep3_bit,
)
from qstack.passes.rep3_phase import (
    Rep3PhaseLowering,
    lower_rep3_phase,
)
from qstack.passes.steane import (
    SteaneLowering,
    lower_steane,
)
from qstack.passes.toy2cliffords import (
    ToyToCliffordsLowering,
    lower_toy_to_cliffords,
)

__all__ = [
    "CliffordPeepholeOptimization",
    "CliffordsToAtomsLowering",
    "CliffordsToH2Lowering",
    "Encoding",
    "LoweringContext",
    "LoweringPass",
    "OptimizationPass",
    "PASS_HISTORY_ATTR",
    "PassError",
    "QubitGroup",
    "Rep3BitLowering",
    "Rep3PhaseLowering",
    "Replacement",
    "SteaneLowering",
    "ToyToCliffordsLowering",
    "lower_cliffords_to_atoms",
    "lower_cliffords_to_h2",
    "lower_rep3_bit",
    "lower_rep3_phase",
    "lower_steane",
    "lower_toy_to_cliffords",
    "optimize_cliffords",
]
