# %%
from qstack import Program, Stack, Kernel
from qstack.layers.apps import *

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
