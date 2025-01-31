# %%
import random

from qstack.layers.cliffords_min import *
from qstack.layer import ClassicDefinition, Outcome, QubitId, Kernel
from qstack import Program, Stack, Kernel

# Pick randomly the operation used for preparation:
op = random.choice([X, H])


def prepare(*, q: QubitId):
    return Kernel(targets=[], instructions=[op(q)])


def fix(m0: Outcome, m1: Outcome, *, q: QubitId):
    instructions = []
    if m1 == 1:
        instructions.append(Z(q))
    if m0 == 1:
        instructions.append(X(q))
    return Kernel(targets=[], instructions=instructions)


Prepare = ClassicDefinition.from_callback(prepare)
Fix = ClassicDefinition.from_callback(fix)

teleport_layer = layer.extend_with(classic={Prepare, Fix})
stack = Stack.create(teleport_layer)

# %%
source = QubitId("q1")
shared = QubitId("q2")
target = QubitId("q3")

program = Program(
    stack=stack,
    kernels=[
        Kernel.allocate(
            target,
            compute=[
                Kernel.allocate(
                    shared,
                    source,
                    compute=[
                        Kernel.continue_with(Prepare(q=source)),
                        H(shared),
                        CX(shared, target),
                        CX(source, shared),
                        H(source),
                    ],
                    continue_with=Fix(q=target),
                ),
            ],
        )
    ],
)

print(program)

# %%
from qstack import QuantumMachine
import qstack.classic_processor
import qstack.emulator

qpu = qstack.emulator.from_layer(teleport_layer)
cpu = qstack.classic_processor.from_layer(teleport_layer)

engine = QuantumMachine(qpu=qpu, cpu=cpu)

# %%
print(op.name)
engine.single_shot(program)

# %%
engine.eval(program).plot_histogram()

# %%
