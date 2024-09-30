# %%
# %%
import logging


logger = logging.getLogger("qstack")
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# %%
from qcir import *
from qstack.layers.clifford.instruction_set import *

circuit = Circuit(
    name="two bells",
    instructions=[
        Attribute("version", "1.0"),
        # Attribute("qubit_count", 4),
        # Attribute("register_count", 4000),
        Tick(),
        Comment("Prepare Bell Pairs"),
        PrepareZero([QubitId(0)]),
        PrepareZero([QubitId(2)]),
        Tick(),
        H([QubitId(0)]),
        Tick(),
        CX([QubitId(0), QubitId(2)]),
        Tick(),
        ApplyPauli([QubitId(1), QubitId(3)], parameters=["X", "Y"]),
        Tick(),
        MeasurePauli([RegisterId(4), QubitId(0), QubitId(1)], parameters=["Z", "Z"]),
        MeasurePauli([RegisterId(5), QubitId(0), QubitId(2)], parameters=["Z", "Z"]),
        Tick(),
        Comment("Or use the built-in gate:"),
        Tick(),
        Comment("Measure qubits into classical registers"),
        MeasureZ([RegisterId(0), QubitId(0)], attributes=[Attribute("p1")]),
        MeasureZ([RegisterId(2), QubitId(1)], attributes=[Attribute("p1")]),
        MeasureZ([RegisterId(3), QubitId(3)], attributes=[Attribute("p2")]),
        MeasureZ([RegisterId(1), QubitId(2)], attributes=[Attribute("p2")]),
    ],
)

# circuit.save()
print(circuit)

# # %%
# import qcir.utils as utils

# utils.inject_random_pauli_noise(circuit)

# %%
from qstack.compilers.standard import compile

t1 = compile(circuit)

# %%
from qstack.layers.clifford.backends import Backend

backend = Backend()
backend.eval(t1).plot_histogram()

# %%
