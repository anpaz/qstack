# %%
from qstack.layers.apps import *


# %%
from qstack.ast import QubitId
from qstack.emulator import StateVectorEmulator

qpu = StateVectorEmulator.from_layer(layer)

qpu.restart(4)
qpu.allocate(QubitId("q1"))
qpu.allocate(QubitId("q2"))
qpu.eval(Mix("q1"))
qpu.eval(Entangle("q1", "q2"))
print(qpu.measure(), qpu.measure())


# %%
from qstack import Program, Stack, Kernel

stack = Stack.create(layer)

program = Program(
    stack=stack,
    kernels=[
        Kernel.allocate(
            "q1",
            "q2",
            compute=[
                Mix("q1"),
                Entangle("q1", "q2"),
            ],
        ),
        Kernel.continue_with(Fix()),
    ],
)

# %%
print(program)

# %%
program.depth

# %%
for k in program.kernels:
    print(k)

# %%
