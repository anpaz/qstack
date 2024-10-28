# %%
from qcir.circuit import QubitId
from qstack.stabilizers import Context, build_lookup_table
from qstack.paulis import *

context = Context(14, 0)

ctl_qubits = [QubitId(i) for i in range(7)]
tgt_qubits = [QubitId(i) for i in range(7, 14)]

for qubits in [ctl_qubits, tgt_qubits]:
    context.add_stabilizer([I, I, I, X, X, X, X], qubits)
    context.add_stabilizer([I, X, X, I, I, X, X], qubits)
    context.add_stabilizer([X, I, X, I, X, I, X], qubits)
    context.add_stabilizer([I, I, I, Z, Z, Z, Z], qubits)
    context.add_stabilizer([I, Z, Z, I, I, Z, Z], qubits)
    context.add_stabilizer([Z, I, Z, I, Z, I, Z], qubits)

# %%
context.stabilizers

# %%
# s = (I, I, I, I, I, I, I, I, I, I, X, X, X, X)

for s in context.stabilizers:
    for i in range(7):
        s = by_cx(s, i, i + 7)
    print(s, tuple(s) in context.stabilizers)
    print("-----")
# %%
stabilizers = context.find_stabilizer_group(tgt_qubits)
table = build_lookup_table(stabilizers)

# %%
syndrome = (0, 0, 1, 0, 0, 0)
table[syndrome]

# %%
