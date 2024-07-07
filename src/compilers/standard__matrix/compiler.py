from ..base_compiler import BaseCompiler as BaseCompiler
from .handlers import PrepareBell, MeasureZ


class Standard2Matrix(BaseCompiler):

    def __init__(self):
        super().__init__(
            {
                PrepareBell(),
                MeasureZ(),
            }
        )
