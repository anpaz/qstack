# %%
import init_logging

# %%
from qcir import *
from qstack.layers.apps.gadgets import *

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
        Comment("Or use the built-in gate:"),
        PrepareBell([QubitId(1), QubitId(3)]),
        Tick(),
        Comment("Measure qubits into classical registers"),
        MeasureZ([RegisterId(0), QubitId(0)], attributes=[Attribute("p1")]),
        MeasureZ([RegisterId(3), QubitId(3)], attributes=[Attribute("p2")]),
        MeasureZ([RegisterId(2), QubitId(1)], attributes=[Attribute("p2")]),
        MeasureZ([RegisterId(1), QubitId(2)], attributes=[Attribute("p1")]),
    ],
)

print(circuit)


# %%
from qstack.compilers.standard import compile

t1 = compile(circuit)
print(t1)


# %%
from qstack.layers.clifford.backends import Backend

backend = Backend()
backend.eval(t1).plot_histogram()


# %%
from qstack.layers.standard.backends.pyQuil import Backend

backend = Backend()
backend.eval(t1).plot_histogram()


# %%
from qstack.compilers.standard.matrix.compiler import compile

t2 = compile(t1)
print(t2)

# %%
from runtimes.matrix.backends.pyQuil import Backend

backend = Backend()
backend.eval(t2, shots=1000).plot_histogram()


# %%
compiler = H2Emulation()
t1 = compiler.compile(circuit)

print(t1)

# %%
emulator = Emulator()
emulator.eval(t1, shots=10)

# %%
import numpy as np

# %%
G = np.array(
    [
        [1, 0, 1, 0, 1, 0, 1],
        [0, 1, 1, 0, 0, 1, 1],
        [0, 0, 0, 1, 1, 1, 1],
        [1, 1, 1, 0, 0, 0, 0],
    ]
)

a = np.array([[0, 0, 1, 1]])

# a.transpose()
# print(a.T)

np.dot(a, G)

# np.dot(G[0], G[0].T)
# %%

X = np.array(
    [
        [0, 1],
        [1, 0],
    ]
)

Z = np.array(
    [
        [1, 0],
        [0, -1],
    ]
)

np.dot(X, X)
# %%
np.dot(Z, X)

# %%
np.dot(X, Z)

# %%
Y = np.array([[0, -1j], [1j, 0]])

np.dot(Y, Y)
# %%
np.dot(X, Y)
# %%
np.dot(Y, X)
# %%
