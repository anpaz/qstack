# %%
import logging


logger = logging.getLogger("qstack")

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

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

machine = local_machine_for(original.stack)
machine.eval(original).plot_histogram()


# %%
from qstack.compilers.toy2cliffords import ToyCompiler

compiler = ToyCompiler()
compiled = compiler.compile(original)

print(compiled)

# %%
try:
    machine.eval(compiled).plot_histogram()
except Exception as e:
    print(e)
    print("This is expected, as the machine is for the original stack...")

# %%
machine = local_machine_for(compiled.stack)
machine.eval(compiled).plot_histogram()


# %%
from qstack.compilers.rep3_trivial import TrivialRepetitionCompiler

compiler = TrivialRepetitionCompiler()
rep3 = compiler.compile(compiled)

print(rep3)

# %%
machine = local_machine_for(rep3.stack)
machine.eval(rep3).plot_histogram()

# %%
compiler = TrivialRepetitionCompiler()
rep3bis = compiler.compile(rep3)

print(rep3bis)


# # %%
# logger.setLevel(logging.DEBUG)

# machine = local_machine_for(rep3bis.stack)
# machine.single_shot(rep3bis)
