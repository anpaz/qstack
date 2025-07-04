from .ast import Kernel as Kernel, QubitId, ClassicInstruction
from .program import Program as Program
from .processors import QPU as QPU
from .machine import QuantumMachine as QuantumMachine

try:
    from IPython import get_ipython
    from . import jupyter  # adjust the import if needed

    ip = get_ipython()
    if ip is not None:
        ip.register_magics(jupyter.QStackMagics)

except ImportError:
    pass  # IPython not installed, ignore
