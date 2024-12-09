# %%
import init_logging

# %%
from qstack.layers.apps.gadgets import *

start = Start("hello world")
print(start)

# %%
zero = PrepareZero("q0")
print(zero)

# %%
one = PrepareOne("q1")
print(one)


# %%
random = PrepareRandom("q2")
print(random)


# %%
m0 = MeasureZ("q0")
print(m0)

# %%
m1 = MeasureZ("q1")
print(m1)

# %%
m2 = MeasureZ("q2")
print(m1)

# %%
program = start | zero
print(program)

# %%
program |= one
print(program)


# %%
program |= m0
program |= m1

print(program)


# %%
from qstack.backend import StateVectorBackend

backend = StateVectorBackend()
backend.single_shot(program)

# %%
backend.eval(program).plot_histogram()


# %%
from qstack.backend import StateVectorBackend

noisy_backend = StateVectorBackend(noise="noise.json")
results = noisy_backend.eval(program, shots=1000)
results.plot_histogram()


# %%
import qstack.layers.rep3_bit.gadgets as gadgets

# %%
prep0 = gadgets.PrepareZero("q0")
print(prep0)

# %%
prep1 = gadgets.PrepareZero("q1")
print(prep1)


# %%
x1 = gadgets.X("q1")
print(x1)

# %%
m0 = gadgets.MeasureZ("q0")
print(m0)

# %%
m1 = gadgets.MeasureZ("q1")
print(m1)

# %%
print(program)


# %%
from qstack.gadget import Gadget

encoded = Gadget(
    name="Hello World (encoded)",
    prepare=[prep0, prep1],
    compute=[x1],
    measure=[m0, m1],
)
print(encoded)


# %%
from qstack.backend import StateVectorBackend

backend = StateVectorBackend()
backend.single_shot(encoded)


# %%
bit, context = noisy_backend.single_shot(encoded)
while bit == (0, 1):
    bit, context = noisy_backend.single_shot(encoded)
    # print('.')

print(bit, context)


# %%
backend.eval(program, shots=1000).plot_histogram()

# %%
noisy_backend = StateVectorBackend(noise="noise.json")
results = noisy_backend.eval(program, shots=1000)
results.plot_histogram()


# %%
