# %%
import qstack.classic_processor

from qstack.layer import ClassicDefinition, ClassicDefinition, Outcome, QubitId
from qstack.ast import Kernel, QuantumInstruction
from qstack.processors import flush


def vote(m1: Outcome, m2: Outcome, m3: Outcome) -> Outcome:
    print("on vote", m1, m2, m3)
    if m1 + m2 + m3 >= 2:
        return 1
    else:
        return 0


def q_flip(m: Outcome, *, q: QubitId):
    print("on q_flip", m)
    if m == 1:
        return Kernel(targets=[], instructions=[QuantumInstruction(name="x", targets=[q])])
    else:
        return None


Vote = ClassicDefinition.from_callback(vote)
QFlip = ClassicDefinition.from_callback(q_flip)

cpu = qstack.classic_processor.ClassicProcessor(instructions={Vote, QFlip})

# %%
cpu.restart()

cpu.collect(0)

cpu.collect(1)
cpu.collect(0)
cpu.collect(1)
cpu.eval(Vote())

cpu.collect(1)
cpu.collect(0)
cpu.collect(0)
cpu.eval(Vote())

print(cpu.eval(QFlip(q=QubitId("q1"))))
print(cpu.eval(QFlip(q=QubitId("q2"))))

print(list(flush(cpu)))
# %%
