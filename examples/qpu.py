# %%
from qstack.layers.toy import *
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
