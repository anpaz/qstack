from ..base_compiler import BaseCompiler as BaseCompiler
from .measure import Measure
from .prepare_zero import PrepareZero
from .rz import RZ
from .rzz import RZZ
from .u1 import U1
from .zz import ZZ


class H2ToMatrix(BaseCompiler):

    def __init__(self):
        super().__init__(
            {
                Measure(),
                PrepareZero(),
                RZ(),
                RZZ(),
                U1(),
                ZZ(),
            }
        )
