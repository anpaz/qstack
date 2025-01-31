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
                Skew("q1", p=0.75),
                Entangle("q1", "q2"),
            ],
        )
    ],
)

print(program)

# %%
from qstack import QuantumMachine
import qstack.classic_processor
import qstack.emulator

qpu = qstack.emulator.from_layer(layer)
cpu = qstack.classic_processor.from_layer(layer)

engine = QuantumMachine(qpu=qpu, cpu=cpu)

engine.eval(program).plot_histogram()

# %%
