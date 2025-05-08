# %%
# This example demonstrates the use of a quantum processor (QPU) in qstack.
# Quantum processors are responsible for executing quantum operations on qubits.
# They simulate or interact with actual quantum hardware to perform computations.
# This example focuses on the QPU interface, which operates independently of the CPU.
# It showcases how to call the different operations of the QPU interface, such as restart, allocate, eval, and measure.
from qstack.layers.toy import layer, Mix, Flip, Entangle
from qstack.ast import QubitId
import qstack.emulator

qpu = qstack.emulator.from_layer(layer)

qpu.restart(4)
qpu.allocate(QubitId("q1"))
qpu.allocate(QubitId("q2"))
qpu.allocate(QubitId("q3"))
qpu.eval(Mix("q1"))
qpu.eval(Flip("q3"))
qpu.eval(Entangle("q1", "q2"))

print(qpu.measure(), qpu.measure(), qpu.measure())

# %%
