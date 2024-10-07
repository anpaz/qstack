# %%
import init_logging

# %%
from qcir import *
from qstack.layers.apps.instruction_set import *

circuit = Circuit(
    [
        # PrepareZero([QubitId(0)]),
        PrepareOne([QubitId(1)]),
        # PrepareRandom([QubitId(2)]),
        PrepareBell([QubitId(3), QubitId(4)]),
        Tick(),
        Comment("Measure qubits into classical registers"),
        Measure([RegisterId(0), QubitId(0)]),
        Measure([RegisterId(1), QubitId(1)]),
        # Measure([RegisterId(2), QubitId(2)]),
        Measure([RegisterId(3), QubitId(3)]),
        Measure([RegisterId(4), QubitId(4)]),
    ]
)

print(circuit)


# %%
from qstack.layers.apps.compiler import compile

t1 = compile(circuit, name="basic example")
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

noise_model = simple_noise_model(0.02)
backend = Backend(noise_model=noise_model)
results = backend.eval(t1)
results.plot_histogram()


# # %%
# results.get_histogram()


# %%
from qstack.layers.repetition.compilers.apps.compiler import compile

t3 = compile(t1)
# print(t3)

# %%
from qstack.layers.cliffords.backend import Backend

backend = Backend()
result = backend.eval(t3)
result.plot_histogram()


# %%
hist = result.get_raw_histogram()
for i in list(hist.items())[:40]:
    print(i)


# %%
from qstack.layers.cliffords.backend import Backend
from qstack.noise import simple_noise_model

noise_model = simple_noise_model(0.02)
backend = Backend(noise_model=noise_model)
result = backend.eval(t3)
result.plot_histogram()

# # %%
# result.get_histogram()


# %%
from qstack.layers.steane.compilers.apps.compiler import compile

t4 = compile(t1)
# print(t4)

# %%
from qstack.layers.cliffords.backend import Backend

backend = Backend()
result = backend.eval(t4)
result.plot_histogram()


# %%
hist = result.get_raw_histogram()
for i in list(hist.items())[:40]:
    print(i)


# %%
from qstack.layers.cliffords.backend import Backend
from qstack.noise import simple_noise_model

noise_model = simple_noise_model(0.02)
backend = Backend(noise_model=noise_model)
result = backend.eval(t4)
result.plot_histogram()
# result.get_raw_histogram()

# %%
