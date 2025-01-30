from dataclasses import dataclass

from pyquil import Program
from pyquil.quilatom import MemoryReference


@dataclass
class Context:
    constructors: dict
    program: Program
    readout: MemoryReference
