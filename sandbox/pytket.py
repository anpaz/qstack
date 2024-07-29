# %%
from pytket.circuit import Circuit
from pytket.circuit.display import render_circuit_jupyter as draw

from pytket.circuit import CustomGateDef

circ = Circuit(3, 1)
circ.H(0)
circ.CX(0, 1)
circ.CX(1, 2)
circ.Rz(0.25, 2)
circ.Measure(2, 0)
draw(circ)


# %%


prepare_bell = CustomGateDef.define(name="|bell⟩", circ=Circuit(2), args=[])


c = Circuit(3)
c.add_custom_gate(prepare_bell, [], [2, 1])
c.measure_register()
draw(c)

# %%
from sympy import Symbol
import numpy as np


m1 = [
    Symbol("a00"),
    Symbol("a01"),
    Symbol("a10"),
    Symbol("a21"),
]

matrix1 = CustomGateDef.define(name="matrix1", circ=Circuit(1), args=m1)
matrix2 = CustomGateDef.define(name="matrix2", circ=Circuit(2), args=[])

x_matrix = [1.0, 0.0, 0.0, 1]


c = Circuit(3)
c.add_custom_gate(matrix1, x_matrix, [2])
# c.measure_register(2)
draw(c)


# %%
