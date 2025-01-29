# %%
from qstack.layers.apps import *
from qstack.ast import QubitId
import qstack.emulator

qpu = qstack.emulator.from_layer(layer)

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
            "result",
            compute=[
                Kernel.allocate(
                    "q1",
                    "q2",
                    compute=[
                        # Flip("q2"),
                        Mix("q1"),
                        Entangle("q1", "q2"),
                    ],
                    continue_with=Fix(q=QubitId("result")),
                )
            ],
        ),
    ],
)

# %%
print(program)

# %%
from qstack import QuantumMachine
import qstack.classic_processor

cpu = qstack.classic_processor.from_layer(layer)
engine = QuantumMachine(qpu=qpu, cpu=cpu)

# %%
engine.single_shot(program)

# %%
engine.eval(program).plot_histogram()
# %%
