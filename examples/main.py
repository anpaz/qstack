# %%
# import init_logging

# %%
from qstack.layers.apps.gadgets import *

program = Start("hello world")

program |= PrepareRandom("q0")
program |= PrepareZero("q1")

program |= Entangle("q0", "q1")

program |= Measure("q0")
program |= Measure("q1")

print(program)


# %%
from qstack.backend import StateVectorBackend

backend = StateVectorBackend()
backend.single_shot(program)

# %%
backend.eval(program, shots=100).plot_histogram()


# %%
from qstack.backend import StateVectorBackend

noisy_backend = StateVectorBackend(noise="noise")
results = noisy_backend.eval(program, shots=1000)
results.plot_histogram()


# %%
from qstack.encoder import encode
import qstack.layers.rep3_bit.gadgets as rep3

encoded = encode(program, rep3)
print(encoded)


# %%
double_encoded = encode(encoded, rep3)
print(double_encoded)

# %%
backend.single_shot(encoded)

# %%
backend.eval(encoded, shots=100).plot_histogram()



Idealized high level program
Can be analyzed

Two noise models, we can compare correctness.
  - 
# # %%
# import qstack.layers.rep3_bit.gadgets as rep3

# prep0 = rep3.PrepareZero("q0")
# prep1 = rep3.PrepareZero("q1")
# prep2 = rep3.PrepareZero("q2")
# h = rep3.X("q2")
# cx = rep3.CX("q2", "q1")
# m0 = rep3.MeasureZ("q0")
# m1 = rep3.MeasureZ("q1")
# m2 = rep3.MeasureZ("q2")

# # print(program)


# # %%
# from qstack.gadget import Gadget

# # TODO:
# # encoded = encode(program, rep3)
# encoded = Gadget(
#     name="Hello World (encoded)",
#     level=1,
#     prepare=[prep0, prep1, prep2],
#     compute=[h, cx],
#     measure=[m0, m1, m2],
#     decode=program.decode,
# )
# print(encoded)


# # %%
# from qstack.backend import StateVectorBackend

# backend = StateVectorBackend(num_qubits=15)
# backend.single_shot(encoded)

# # %%

# # %%
# backend.eval(encoded, shots=100).plot_histogram()

# # %%
# noisy_backend = StateVectorBackend(noise="noise.json")
# bit, context = noisy_backend.single_shot(encoded)
# while bit == (0, 1):
#     bit, context = noisy_backend.single_shot(encoded)
#     # print('.')

# print(bit, context)

# # %%
# results = noisy_backend.eval(encoded, shots=1000)
# results.plot_histogram()


# # %%
