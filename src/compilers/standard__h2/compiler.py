from ..base_compiler import BaseCompiler as BaseCompiler
from .handlers import PrepareBell, MeasureZ


class StandardToH2(BaseCompiler):

    def __init__(self):
        super().__init__(
            {
                PrepareBell(),
                MeasureZ(),
            }
        )
