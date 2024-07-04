# %%
%load_ext autoreload
%autoreload 2

# %%
from qcir import Circuit, Instruction, QubitId, Tick, Comment, RegisterId, Attribute

circuit = Circuit(
    name="teleport",
    instruction_set="standard",
    instructions=[
        Attribute("version", "1.0"),
        Attribute("qubit_count", 2),
        Attribute("circuit_depth", 2),
        Tick(),
        Comment("Prepare Bell"),
        Instruction("prepare_bell", [QubitId(0), QubitId(1)]),
        Tick(),
        Comment("Measure qubits into classical registers"),
        Instruction("mz", [QubitId(0), RegisterId(0)]),
        Instruction("mz", [QubitId(1), RegisterId(1)]),
    ],
)

print(circuit)


# %%
from qstack import machine

qvm = machine.create_qvm('standard')

# %%
emulator = qvm.create_emulator()

# %%
emulator.eval(circuit, shots=10)
# %%
