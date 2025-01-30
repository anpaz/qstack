from dataclasses import dataclass

from .layer import Layer
from .ast import Kernel


@dataclass(frozen=True)
class Compiler:
    name: str
    source: Layer
    target: Layer

    def eval(kernel: Kernel) -> Kernel:
        pass
