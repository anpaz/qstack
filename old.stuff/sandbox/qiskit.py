# %%
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.circuit import Gate
import numpy as np


# Define a custom gate
class PrepareBell(Gate):
    def __init__(self):
        super().__init__("|bell⟩", 2, [])  # 'custom_gate' is the name, 2 is the number of qubits


# %%

v_type = complex | float | int


# fmt: off
class Matrix1(Gate):
    def __init__(self, matrix):
        super().__init__('matrix1', 1, [matrix])


    def __array__(self, dtype=None, copy=None):
        if copy is False:
            raise ValueError("unable to avoid copy while creating an array as requested")
        return self.params[0]


# fmt: off
class Matrix2(Gate):
    def __init__(self, matrix):
        super().__init__('matrix2', 2, [matrix])

    def __array__(self, dtype=None, copy=None):
        if copy is False:
            raise ValueError("unable to avoid copy while creating an array as requested")
        return self.params[0]


#%%
from qiskit.circuit import Parameter, Measure
from qiskit.transpiler import Target, InstructionProperties

DEFAULT_ERROR = 0.001
DEFAULT_DURATION = 5e-7

target = Target(num_qubits=3)
target.add_instruction(
    Matrix1(Parameter('matrix')),
    {
        (0,): InstructionProperties(error=DEFAULT_ERROR, duration=DEFAULT_DURATION),
        (1,): InstructionProperties(error=DEFAULT_ERROR, duration=DEFAULT_DURATION),
        (2,): InstructionProperties(error=DEFAULT_ERROR, duration=DEFAULT_DURATION),
    }
)
target.add_instruction(
    Matrix2(Parameter('matrix')),
    {
        (0,1): InstructionProperties(error=DEFAULT_ERROR, duration=DEFAULT_DURATION),
        (0,2): InstructionProperties(error=DEFAULT_ERROR, duration=DEFAULT_DURATION),
        (1,0): InstructionProperties(error=DEFAULT_ERROR, duration=DEFAULT_DURATION),
        (1,2): InstructionProperties(error=DEFAULT_ERROR, duration=DEFAULT_DURATION),
        (2,0): InstructionProperties(error=DEFAULT_ERROR, duration=DEFAULT_DURATION),
        (2,1): InstructionProperties(error=DEFAULT_ERROR, duration=DEFAULT_DURATION),
    }
)
target.add_instruction(
    Measure(),
    {
        (0,): InstructionProperties(error=.001, duration=5e-5),
        (1,): InstructionProperties(error=.002, duration=6e-5),
        (2,): InstructionProperties(error=.2, duration=5e-7)
    }
)
print(target)


# %%

# Create a quantum circuit
qr = QuantumRegister(3, 'q')
cr = ClassicalRegister(2)
qc = QuantumCircuit(qr, cr)

# Add the custom gate to the circuit
bell = PrepareBell()
qc.append(bell, [qr[1], qr[2]])
qc.barrier()
qc.measure(qr[0], cr[0])
qc.measure(qr[1], cr[1])
qc.barrier()
# Draw the circuit
print(qc.draw())

#%%
from qiskit.transpiler.passes import Decompose
from qiskit.transpiler import PassManager, TransformationPass



from qiskit.circuit.library.standard_gates import U3Gate, CXGate

# Define a custom decomposition pass
class DecomposePrepareBell(TransformationPass):
    def run(self, dag):
        for node in dag.named_nodes('|bell⟩'):
            dag.substitute_node_with_dag(node, self.decompose_bell(dag.qregs, node.qargs))
        return dag

    def decompose_bell(self, qregs, qargs):
        # qr = QuantumRegister(2, 'q')
        qc = QuantumCircuit(qregs['q'])
        # Decompose the custom two-qubit gate into basis gates (example decomposition)
        qc.append(U3Gate(np.pi/2, 0, np.pi), [qargs[0]])
        qc.append(CXGate(), [qargs[0], qargs[1]])
        qc.append(U3Gate(np.pi/2, np.pi/2, np.pi/2), [qargs[1]])
        return qc




# %%
from qiskit import transpile

# Define a pass manager to decompose custom gates
pass_manager = PassManager(DecomposePrepareBell())
pass_manager.run(qc)


# qc2 = transpile(qc,  basis_gates=['matrix1', 'matrix2'], pass_manager=pass_manager)
print(qc)


# %%
# from qiskit import QuantumCircuit, transpile
# # from qiskit.transpiler import PassManager
# # from qiskit.transpiler.passes import Unroller

# # Define a quantum circuit
# qc = QuantumCircuit(2)
# qc.h(0)
# qc.cx(0, 1)
# qc.rx(0.5, 1)

# # Define the basis gates
# basis_gates = ['u3', 'cx']

# # Transpile the circuit to the specified basis gates
# transpiled_qc = transpile(qc, basis_gates=basis_gates, optimization_level=3)

# # Print the transpiled circuit
# print(transpiled_qc)

# %%
print(qc)

# %%
import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, transpile
from qiskit.circuit import Gate
from qiskit.circuit.library.standard_gates import U3Gate, CXGate
from qiskit.transpiler import PassManager, TransformationPass
from qiskit.dagcircuit import DAGCircuit
from qiskit.converters import circuit_to_dag, dag_to_circuit

# Define a custom two-qubit gate
class CustomTwoQubitGate(Gate):
    def __init__(self):
        super().__init__('custom_two_qubit', 2, [])

# Define a custom decomposition pass
class DecomposeCustomTwoQubit(TransformationPass):
    def run(self, dag: DAGCircuit) -> DAGCircuit:
        for node in dag.named_nodes('custom_two_qubit'):
            qargs = node.qargs
            dag.substitute_node_with_dag(node, circuit_to_dag(self.decompose_custom_two_qubit(qargs)))
        return dag

    def decompose_custom_two_qubit(self, qargs):
        qr = QuantumRegister(2, 'q')
        qc = QuantumCircuit(qr)
        # Decompose the custom two-qubit gate into basis gates (example decomposition)
        qc.append(U3Gate(np.pi/2, 0, np.pi), [qargs[0]])
        qc.append(CXGate(), [qargs[0], qargs[1]])
        qc.append(U3Gate(np.pi/2, np.pi/2, np.pi/2), [qargs[1]])
        return qc

# Create a quantum circuit with the custom two-qubit gate
qc = QuantumCircuit(2)
qc.append(CustomTwoQubitGate(), [0, 1])

# Define a pass manager to decompose custom gates
pass_manager = PassManager(DecomposeCustomTwoQubit())

# Apply the decomposition pass to the circuit
decomposed_circuit = pass_manager.run(qc)
print(decomposed_circuit)
# # Transpile the decomposed circuit
# transpiled_qc = transpile(decomposed_circuit, basis_gates=['u3', 'cx'])

# # Print the transpiled circuit
# print(transpiled_qc)

# %%
