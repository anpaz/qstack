# %%
# This example demonstrates the use of a classical processor (CPU) in qstack.
# Classical processors are used to handle classical computations that interact with quantum programs.
# They process measurement results, apply classical logic, and execute classical instructions.
# This example focuses on the CPU interface, which operates independently of the QPU.
# It showcases how to call the different operations of the CPU interface, such as restart, collect, eval, and consume.
from qstack.layer import ClassicDefinition, QubitId
from qstack.ast import Kernel, QuantumInstruction
from qstack.processors import flush
from qstack.classic_processor import ClassicalContext, ClassicProcessor


# Define a classical voting function.
# This function takes three measurement results from the stack and determines the majority vote.
# If at least two of the results are 1, the vote is 1; otherwise, it is 0.
# The `context.consume()` method consumes the top measurement result from the stack.
# This is used to retrieve classical outcomes for further processing.
# The `context.collect(x)` method adds an outcome `x` to the top of the stack.
# This is used to store classical results for later use in the program.
def vote(context: ClassicalContext):
    m1 = context.consume()  # Pop the latest measurement from the stack.
    m2 = context.consume()  # Pop the next measurement from the stack.
    m3 = context.consume()  # Pop the next measurement from the stack.

    print("on vote", m1, m2, m3)
    if m1 + m2 + m3 >= 2:
        context.collect(1)  # Add a vote of 1 to the stack if the majority is 1.
    else:
        context.collect(0)  # Add a vote of 0 to the stack otherwise.


# Define a classical function to conditionally flip a qubit's state.
# If the consumed measurement result is 1, an X gate (quantum NOT) is applied to the qubit.
def q_flip(context: ClassicalContext, *, q: QubitId):
    m = context.consume()  # Consume a measurement result.
    print("on q_flip", m)
    if m == 1:
        return Kernel(targets=[], instructions=[QuantumInstruction(name="x", targets=[q])])


# Create classical definitions for the vote and q_flip functions.
Vote = ClassicDefinition.from_callback(vote)
QFlip = ClassicDefinition.from_callback(q_flip)

# Initialize a classical processor with the defined instructions.
# The classical processor is responsible for executing classical logic in a quantum-classical hybrid program.
cpu = ClassicProcessor(instructions={Vote, QFlip})

# %%
# Restart the classical processor to clear its state.
cpu.restart()

# Collect initial votes and evaluate the voting logic.
# The collect method stores classical data (e.g., measurement results) for processing.
cpu.collect(0)

cpu.collect(1)
cpu.collect(0)
cpu.collect(1)
cpu.eval(Vote())  # Evaluate the voting logic with the collected data.

cpu.collect(1)
cpu.collect(0)
cpu.collect(0)
cpu.eval(Vote())  # Evaluate the voting logic again with new data.

# Consume the last two votes and conditionally flip the state of qubits.
# The q_flip function applies an X gate to the specified qubit if the consumed vote is 1.
print(cpu.eval(QFlip(q=QubitId("q1"))))
print(cpu.eval(QFlip(q=QubitId("q2"))))

# Flush the processor's state and print the remaining data.
# The flush function clears all remaining data in the processor and returns it as a tuple.
print(tuple(flush(cpu)))

# %%
