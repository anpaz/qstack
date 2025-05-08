# %%
# This example demonstrates the use of the Steane code for quantum error correction using qstack.
# The Steane code is a 7-qubit error-correcting code that can correct single-qubit errors.
# The clifford_min layer is a minimal abstraction layer for Clifford operations, providing essential gates like H, CX, and Pauli gates.
# It is designed for efficient simulation and execution of quantum programs.
import logging

# Set up logging to monitor the execution of the program.
logger = logging.getLogger("qstack")

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# %%
# Import necessary components from qstack.
from qstack.layers.cliffords_min import *
from qstack import Program, Stack, Kernel

# Create a stack using the cliffords_min layer.
stack = Stack.create(layer)

# Define a simple quantum program to be compiled with error correction.
original = Program(
    stack=stack,
    kernels=[Kernel.allocate("q1", compute=[])],  # Allocate a single qubit.
)

# Print the original program to visualize its structure.
print(original)

# %%
# Compile the program using the Steane error-correcting compiler.
from qstack.compilers.steane import SteaneCompiler

compiler = SteaneCompiler()
compiled = compiler.compile(original)

# Print the compiled program to see the error-corrected version.
print(compiled)

# %%
# Set up a local quantum machine to execute the compiled program.
# Each machine in qstack is created to target a specific stack or instruction set.
# This ensures that the machine can correctly interpret and execute the program's instructions.
logger.setLevel(logging.DEBUG)

machine = local_machine_for(compiled.stack)

# Perform a single-shot execution of the error-corrected program.
# A single-shot execution runs the program once and returns the measurement outcomes.
# This is useful for observing the result of a single execution of the quantum program.
machine.single_shot(compiled)

logger.setLevel(logging.INFO)

# %%
# Define a more complex program to demonstrate error correction in action.
original = Program(
    stack=stack,
    kernels=[
        Kernel.allocate(
            "q1",
            "q2",
            compute=[
                H("q1"),  # Apply a Hadamard gate to the first qubit.
                CX("q1", "q2"),  # Entangle the first and second qubits.
            ],
        )
    ],
)

# Print the original program.
print(original)

# %%
# Execute the original program without error correction and plot the results.
from qstack.machine import local_machine_for

machine = local_machine_for(stack)
machine.eval(original).plot_histogram()

# %%
# Compile the program with the Steane error-correcting compiler.
compiled = compiler.compile(original)

# Print the compiled program.
print(compiled)

# %%
# Execute the error-corrected program and plot the results.
logger.setLevel(logging.DEBUG)

machine = local_machine_for(compiled.stack)
machine.single_shot(compiled)

logger.setLevel(logging.INFO)
machine.eval(compiled, shots=100).plot_histogram()

# %%
# Demonstrate the state preparation routine for the Steane code.
from qstack.ast import QubitId

# Define the 7 qubits used in the Steane code.
q = [QubitId(i) for i in range(7)]

# Define the instructions for preparing the Steane code state.
instructions = [
    H(q[4]),  # Apply a Hadamard gate to the 5th qubit.
    H(q[5]),  # Apply a Hadamard gate to the 6th qubit.
    H(q[6]),  # Apply a Hadamard gate to the 7th qubit.
    CX(q[4], q[0]),  # Entangle the 5th qubit with the 1st qubit.
    CX(q[4], q[1]),  # Entangle the 5th qubit with the 2nd qubit.
    CX(q[4], q[3]),  # Entangle the 5th qubit with the 4th qubit.
    CX(q[5], q[0]),  # Entangle the 6th qubit with the 1st qubit.
    CX(q[5], q[2]),  # Entangle the 6th qubit with the 3rd qubit.
    CX(q[5], q[3]),  # Entangle the 6th qubit with the 4th qubit.
    CX(q[6], q[1]),  # Entangle the 7th qubit with the 2nd qubit.
    CX(q[6], q[2]),  # Entangle the 7th qubit with the 3rd qubit.
    CX(q[6], q[3]),  # Entangle the 7th qubit with the 4th qubit.
]

# Create a program for the state preparation routine.
encoder = Program(stack=stack, kernels=[Kernel(targets=q, instructions=instructions)])

# Execute the state preparation routine and print the resulting histogram.
machine = local_machine_for(stack)
for k, v in machine.eval(encoder).get_histogram().items():
    print(k, v)

# %%
