from dataclasses import dataclass

from .prepare_zero import PrepareZero
from .u1 import U1
from .measure_z import MeasureZ
from .rzz import RZZ
from .zz import ZZ
from .rz import RZ


@dataclass(frozen=True)
class H2InstructionSet:

    instruction_set = {
        PrepareZero(),
        U1(),
        RZ(),
        RZZ(),
        ZZ(),
        MeasureZ(),
    }
