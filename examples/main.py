# %%
import init_logging

# %%
from qcir import *
from qstack.layers.apps.instruction_set import *

circuit = Circuit(
    name="sample app",
    instructions=[
        Attribute("version", "1.0"),
        # Attribute("qubit_count", 4),
        # Attribute("register_count", 4000),
        Tick(),
        PrepareZero([QubitId(0)]),
        PrepareOne([QubitId(1)]),
        # PrepareRandom([QubitId(2)]),
        # PrepareBell([QubitId(3), QubitId(4)]),
        Tick(),
        Comment("Measure qubits into classical registers"),
        Measure([RegisterId(0), QubitId(0)]),
        Measure([RegisterId(1), QubitId(1)]),
        # Measure([RegisterId(2), QubitId(2)]),
        # Measure([RegisterId(3), QubitId(3)]),
        # Measure([RegisterId(4), QubitId(4)]),
    ],
)

print(circuit)
# circuit.save()


# %%
from qstack.layers.apps.compiler import compile

t1 = compile(circuit)
print(t1)

# %%
from qstack.layers.apps.backend import Backend

backend = Backend()
backend.eval(t1).plot_histogram()

# %%
from qstack.layers.cliffords.compilers.apps.compiler import compile

t2 = compile(t1)
print(t2)

# %%
from qstack.layers.cliffords.backend import Backend

backend = Backend()
backend.eval(t2).plot_histogram()


# %%
from qstack.layers.apps.backend import Backend
from qstack.noise import simple_noise_model

noise_model = simple_noise_model(0.1)
backend = Backend(noise_model=noise_model)
backend.eval(t1).plot_histogram()


# %%
from qstack.layers.repetition.compilers.apps.compiler import compile

t3 = compile(t1)
print(t3)

# %%
from qstack.layers.cliffords.backend import Backend

backend = Backend()
backend.eval(t3).plot_histogram()

# %%
backend.eval(t3).get_raw_histogram()


# %%
from qstack.layers.cliffords.backend import Backend

backend = Backend(noise_model=noise_model)
result = backend.eval(t3)
result.plot_histogram()


# %%
decoder = t3.decoder

# %%
v = (False, False, 0, 0, 1, 1, 1, 1, 0, 0)
decoder(v), v

# %%
v = (False, False, 0, 0, 1, 0, 1, 0, 0, 1)
decoder(v), v


# %%
