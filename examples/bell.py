# %%
from qstack.layers.toy import *
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
        )
    ],
)

print(program)

# %%
from qstack.machine import local_machine_for

machine = local_machine_for(stack)

# %%
machine.single_shot(program)

# %%
machine.eval(program).plot_histogram()

# %%
