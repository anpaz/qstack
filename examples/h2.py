# %%
import math

# init_logging.debug_qstack()

# %%
from qcir import Circuit, Instruction, QubitId, Tick, Comment, RegisterId, Attribute

circuit = Circuit(
    name="teleport",
    instruction_set="h2",
    instructions=[
        Attribute("version", "1.0"),
        # Attribute("qubit_count", 4),
        # Attribute("register_count", 4),
        Tick(),
        Instruction("|0⟩", [QubitId(0)]),
        Instruction("|0⟩", [QubitId(1)]),
        Tick(),
        Instruction("u1", parameters=[math.pi, 0.0], targets=[QubitId(0)], comment=Comment("X")),
        Tick(),
        Instruction("mz", [QubitId(0), RegisterId(0)]),
        Instruction("mz", [QubitId(1), RegisterId(1)]),
    ],
)

print(circuit)


# %%
import qstack

emulator = qstack.create_qvm("h2").create_emulator()
emulator.eval(circuit, shots=10)

# %%
