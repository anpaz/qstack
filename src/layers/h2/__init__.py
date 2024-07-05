from dataclasses import dataclass

from .prepare_zero import PrepareZero
from .u1 import U1
from .measure_z import MeasureZ


@dataclass(frozen=True)
class H2InstructionSet:

    instruction_set = {
        U1(),
        PrepareZero(),
        MeasureZ(),
    }
