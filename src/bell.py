# %%
from qstack import Program, Stack, QuantumKernel
from qstack.layers.apps import *

stack = Stack.create(layer)

program = Program(
    stack=stack,
    kernels=[
        QuantumKernel.allocate(
            "q1",
            "q2",
            compute=[
                Mix("q1"),
                Entangle("q1", "q2"),
            ],
        ),
    ],
)

# %%
print(program)

# %%
program.depth

# %%
