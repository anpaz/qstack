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
from qstack.machine import local_machine_for, QuantumMachine
from qstack.emulator import from_stack

machine = QuantumMachine(qpu=from_stack(stack), cpu=local_machine_for(stack).cpu)

# %%
machine.single_shot(program)

# %%
machine.eval(program).plot_histogram()

# %%
# Define a noise channel (example: depolarizing noise with error probability 0.1)
from qstack.noise import DepolarizingNoise

noise_channel = DepolarizingNoise(error_probability=0.2)

# Use the noisy emulator with the specified noise channel
machine = QuantumMachine(qpu=from_stack(stack, noise=noise_channel), cpu=local_machine_for(stack).cpu)
machine.eval(program).plot_histogram()


# %%
