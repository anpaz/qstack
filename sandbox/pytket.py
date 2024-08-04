# %%
from pytket.circuit import Circuit, CircBox, Unitary1qBox, Unitary2qBox
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
# class PrepareBell(CircBox):
#     def __init__(self):
#         super().__init__(Circuit(2, name="|bell⟩"))


# prepare_bell = CustomGateDef.define(name="|bell⟩", circ=Circuit(2), args=[])
prepare_bell = CircBox(Circuit(2, name="|bell⟩"))

c = Circuit(4, 4)
# c.add_custom_gate(prepare_bell, [], [2, 1])
c.add_gate(prepare_bell, [0, 2])
c.add_gate(prepare_bell, [1, 3])
c.Measure(0, 0)
c.Measure(1, 1)
c.Measure(2, 2)
c.Measure(3, 3)
draw(c)

# %%
from pytket.predicates import CompilationUnit


cu = CompilationUnit(c)
cu.circuit

# #%%
# from pytket.passes import DecomposeBoxes

# p = DecomposeBoxes()
# p.to_dict()

# %%
import numpy as np
import math


def standard_matrix_transform(circ: Circuit) -> Circuit:
    sqrt1_2 = math.sqrt(1.0 / 2.0)

    h_matrix = np.asarray(
        [
            [sqrt1_2, sqrt1_2],
            [sqrt1_2, -sqrt1_2],
        ]
    )
    H = Unitary1qBox(h_matrix)

    cx_matrix = np.asarray(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0, 0.0],
        ]
    )
    CX = Unitary2qBox(cx_matrix)

    # matrix2 = CustomGateDef.define(name="matrix2", circ=Circuit(2), args=[])

    n_qubits = circ.n_qubits
    circ_prime = Circuit(n_qubits, circ.n_bits, f"{circ.name}::matrix")  # Define a replacement circuit

    for cmd in circ.get_commands():
        qubit_list = cmd.qubits  # Qubit(s) our gate is applied on (as a list)
        if isinstance(cmd.op, CircBox) and cmd.op.circuit_name == "|bell⟩":
            # If cmd is a Z gate, decompose to a H, X, H sequence.
            circ_prime.add_gate(H, [qubit_list[0]])
            circ_prime.add_gate(CX, [qubit_list[0], qubit_list[1]])
        else:
            # Otherwise, apply the gate as usual.
            circ_prime.add_gate(cmd.op.type, cmd.op.params, args=cmd.args)

    return circ_prime


c2 = standard_matrix_transform(c)
draw(c2)
#
# c2

# #%%
# from pytket.utils import Graph
# g = Graph(cu.circuit)

# g.get_DAG()


# %%
