# %%
# This example demonstrates the creation of a Bell state using qstack.
# A Bell state is a maximally entangled quantum state of two qubits.
# The program uses a toy layer to define the quantum operations.
from qstack.layers.toy import *
from qstack import Program, Stack, Kernel

# Create a stack using the toy layer.
stack = Stack.create(layer)

# Define a quantum program that allocates two qubits and entangles them.
program = Program(
    stack=stack,
    kernels=[
        Kernel.allocate(
            "q1",  # First qubit
            "q2",  # Second qubit
            compute=[
                Mix("q1"),  # Apply a mixing operation to the first qubit.
                Entangle("q1", "q2"),  # Entangle the first and second qubits.
            ],
        )
    ],
)

# Print the program to visualize its structure.
print(program)

# %%
# Set up a local quantum machine to execute the program.
# Each machine in qstack is created to target a specific stack or instruction set.
# This ensures that the machine can correctly interpret and execute the program's instructions.
from qstack.machine import local_machine_for

machine = local_machine_for(stack)

# %%
# Perform a single-shot execution of the program.
# A single-shot execution runs the program once and returns the measurement outcomes.
# This is useful for observing the result of a single execution of the quantum program.
machine.single_shot(program)

# %%
# Evaluate the program multiple times and plot the resulting histogram.
machine.eval(program).plot_histogram()

# %%
