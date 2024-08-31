# %%
import init_logging

# %%
from qcir import *
from runtimes.standard.instruction_set import *

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
        MeasureZ([QubitId(0), RegisterId(0)], attributes=[Attribute("p1")]),
        MeasureZ([QubitId(1), RegisterId(1)], attributes=[Attribute("p2")]),
        MeasureZ([QubitId(2), RegisterId(2)], attributes=[Attribute("p1")]),
        MeasureZ([QubitId(3), RegisterId(3)], attributes=[Attribute("p2")]),
    ],
)

print(circuit)


# %%
from compilers.standard import compile

t1 = compile(circuit)
print(t1)


# %%
from runtimes.standard.backends.pyQuil import Backend

backend = Backend()

backend.start()
for outcome in backend.eval(t1, shots=10):
    print(outcome)


# %%
from compilers.standard.matrix.compiler import compile

t2 = compile(t1)
print(t2)


# %%
from runtimes.matrix.backends.pyQuil import Backend

backend = Backend()

backend.start()
for outcome in backend.eval(t2, shots=10):
    print(outcome)

# %%
print(backend.memory)

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
