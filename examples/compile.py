# %%
from qstack.ast import QubitId
from qstack.layers.toy import *
from qstack import Program, Stack, Kernel


def fix(*, q: QubitId):
    return Kernel(targets=[], instructions=[Flip(q)])


Fix = ClassicDefinition.from_callback(fix)

layer = layer.extend_with(classic={Fix})

stack = Stack.create(layer)

original = Program(
    stack=stack,
    kernels=[
        Kernel.allocate(
            "q1",
            compute=[
                Kernel.allocate(
                    "q2",
                    compute=[
                        Mix("q1"),
                        Entangle("q1", "q2"),
                    ],
                    continue_with=Fix(q="q1"),
                )
            ],
        )
    ],
)

print(original)

# %%
from qstack.machine import local_engine_for

engine = local_engine_for(original.stack)
engine.eval(original).plot_histogram()


# %%
from qstack.compilers.toy2cliffords import ToyCompiler

compiler = ToyCompiler()
compiled = compiler.compile(original)

print(compiled)

# %%
try:
    engine.eval(compiled).plot_histogram()
except Exception as e:
    print("This is expected, as the engine is for the original stack:")
    print(e)

# %%
engine = local_engine_for(compiled.stack)

# %%
engine.eval(compiled).plot_histogram()

# %%
