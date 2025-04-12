# %%
from qstack.layers.cliffords_min import *
from qstack import Program, Stack, Kernel

stack = Stack.create(layer)

original = Program(
    stack=stack,
    kernels=[
        Kernel.allocate(
            "q1",
            # "q2",
            compute=[
                # X("q1"),
                # CX("q1", "q2"),
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
machine = local_machine_for(compiled.stack)
for key, v in machine.eval(compiled, shots=100).get_histogram().items():
    print(key, v)


# %%
