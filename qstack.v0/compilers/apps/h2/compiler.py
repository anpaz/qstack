from ..base_compiler import BaseCompiler as BaseCompiler
from .handlers import PrepareBell, MeasureZ, PrepareZero, Hadamard, CtrlX


class StandardToH2(BaseCompiler):

    def __init__(self):
        super().__init__(
            {
                PrepareBell(),
                PrepareZero(),
                Hadamard(),
                CtrlX(),
                MeasureZ(),
            }
        )
