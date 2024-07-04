from dataclasses import dataclass
from .measure_z import MeasureZ
from .prepare_bell import PrepareBell


@dataclass(frozen=True)
class StandardInstructionSet:

    instruction_set = {
        MeasureZ(),
        PrepareBell(),
    }
