# %%
import stim

circuit = stim.Circuit()

# First, the circuit will initialize a Bell pair.
circuit.append("A", [0])
circuit.append("B", [0, 1])

# Then, the circuit will measure both qubits of the Bell pair in the Z basis.
circuit.append("M", [0])
circuit.append("M", [1])

# %%
circuit.diagram()

# %%
sampler = circuit.compile_sampler()
print(sampler.sample(shots=10))
# %%
