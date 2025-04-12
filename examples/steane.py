# %%
import logging


logger = logging.getLogger("qstack")

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


# %%
from qstack.layers.cliffords_min import *
from qstack import Program, Stack, Kernel

stack = Stack.create(layer)

original = Program(
    stack=stack,
    kernels=[Kernel.allocate("q1", compute=[])],
)

print(original)

# %%
from qstack.compilers.steane import SteaneCompiler

compiler = SteaneCompiler()
compiled = compiler.compile(original)


print(compiled)


# %%
logger.setLevel(logging.DEBUG)

machine = local_machine_for(compiled.stack)
machine.single_shot(compiled)

logger.setLevel(logging.INFO)

# %%
from qstack.layers.cliffords_min import *
from qstack import Program, Stack, Kernel

stack = Stack.create(layer)

original = Program(
    stack=stack,
    kernels=[
        Kernel.allocate(
            "q1",
            "q2",
            compute=[
                H("q1"),
                CX("q1", "q2"),
            ],
        )
    ],
)

print(original)

# %%
from qstack.machine import local_machine_for

machine = local_machine_for(stack)
machine.eval(original).plot_histogram()

# %%
from qstack.compilers.steane import SteaneCompiler

compiler = SteaneCompiler()
compiled = compiler.compile(original)


print(compiled)


# %%
logger.setLevel(logging.DEBUG)

machine = local_machine_for(compiled.stack)
machine.single_shot(compiled)


# %%
logger.setLevel(logging.INFO)
machine.eval(compiled, shots=100).plot_histogram()

# %%
## The state prep routing for Steane:
from qstack.machine import local_machine_for
from qstack.ast import QubitId

q = [QubitId(i) for i in range(7)]
instructions = [
    H(q[4]),
    H(q[5]),
    H(q[6]),
    CX(q[4], q[0]),
    CX(q[4], q[1]),
    CX(q[4], q[3]),
    CX(q[5], q[0]),
    CX(q[5], q[2]),
    CX(q[5], q[3]),
    CX(q[6], q[1]),
    CX(q[6], q[2]),
    CX(q[6], q[3]),
]

encoder = Program(stack=stack, kernels=[Kernel(targets=q, instructions=instructions)])

machine = local_machine_for(stack)
for k, v in machine.eval(encoder).get_histogram().items():
    print(k, v)
