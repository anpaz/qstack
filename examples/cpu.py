# %%
from qstack.layer import ClassicDefinition, ClassicDefinition, QubitId
from qstack.ast import Kernel, QuantumInstruction
from qstack.processors import flush
from qstack.classic_processor import ClassicalContext, ClassicProcessor


def vote(context: ClassicalContext):
    m1 = context.consume()
    m2 = context.consume()
    m3 = context.consume()

    print("on vote", m1, m2, m3)
    if m1 + m2 + m3 >= 2:
        context.collect(1)
    else:
        context.collect(0)


def q_flip(context: ClassicalContext, *, q: QubitId):
    m = context.consume()
    print("on q_flip", m)
    if m == 1:
        return Kernel(targets=[], instructions=[QuantumInstruction(name="x", targets=[q])])


Vote = ClassicDefinition.from_callback(vote)
QFlip = ClassicDefinition.from_callback(q_flip)

cpu = ClassicProcessor(instructions={Vote, QFlip})

# %%
cpu.restart()

# final outcome
cpu.collect(0)

cpu.collect(1)
cpu.collect(0)
cpu.collect(1)
cpu.eval(Vote())

cpu.collect(1)
cpu.collect(0)
cpu.collect(0)
cpu.eval(Vote())

# consume last two votes:
print(cpu.eval(QFlip(q=QubitId("q1"))))
print(cpu.eval(QFlip(q=QubitId("q2"))))

print(tuple(flush(cpu)))

# %%
