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
                    "q3",
                    compute=[
                        Mix("q2"),
                        Flip("q3"),
                    ],
                    continue_with=Fix(q="q1"),
                )
            ],
        )
    ],
)

print(original)

# %%
from qstack.machine import local_machine_for

engine = local_machine_for(original.stack)
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
    print(e)
    print("This is expected, as the engine is for the original stack...")

# %%
engine = local_machine_for(compiled.stack)
engine.eval(compiled).plot_histogram()


# %%
from qstack.compilers.rep3_trivial import TrivialRepetitionCompiler

compiler = TrivialRepetitionCompiler()
rep3 = compiler.compile(compiled)

print(rep3)

# %%
engine = local_machine_for(rep3.stack)
engine.eval(rep3).plot_histogram()

# %%
compiler = TrivialRepetitionCompiler()
rep3bis = compiler.compile(rep3)

print(rep3bis)

# %%
