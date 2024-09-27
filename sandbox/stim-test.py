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
from runtimes.standard.instruction_set import *
from runtimes.clifford.instruction_set import MeasurePauli, ApplyPauli

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
        Hadamard([QubitId(0)]),
        Tick(),
        CtrlX([QubitId(0), QubitId(2)]),
        Tick(),
        ApplyPauli([QubitId(1), QubitId(3)], parameters=["X", "Y"]),
        Tick(),
        MeasurePauli([RegisterId(4), QubitId(0), QubitId(1)], parameters=["Z", "Z"]),
        MeasurePauli([RegisterId(5), QubitId(0), QubitId(2)], parameters=["Z", "Z"]),
        Tick(),
        Comment("Or use the built-in gate:"),
        # PrepareBell([QubitId(1), QubitId(3)]),
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
from compilers.standard import compile

t1 = compile(circuit)


from runtimes.clifford.backends import Backend

backend = Backend()
backend.eval(t1).plot_histogram()

# %%
