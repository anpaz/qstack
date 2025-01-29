from dataclasses import dataclass
from .ast import Kernel
from .stack import Stack


@dataclass(frozen=True)
class Program:
    stack: Stack
    kernels: tuple[Kernel]

    @property
    def depth(self):
        return max(k.depth for k in self.kernels)

    def __str__(self):
        attributes = ["@stack: " + str(self.stack)]
        kernels = [str(k) for k in self.kernels]

        return "\n".join(attributes + ["---"] + kernels)
