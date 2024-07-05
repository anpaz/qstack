# %%
import init_logging

init_logging.debug_qstack()

# %%
from qcir import Circuit, Instruction, QubitId, Tick, Comment, RegisterId, Attribute

circuit = Circuit(
    name="teleport",
    instruction_set="standard",
    instructions=[
        Attribute("version", "1.0"),
        # Attribute("qubit_count", 4),
        # Attribute("register_count", 4),
        Tick(),
        Comment("Prepare Bell"),
        Instruction("|bell⟩", [QubitId(0), QubitId(1)]),
        Instruction("|bell⟩", [QubitId(2), QubitId(3)]),
        Tick(),
        Comment("Measure qubits into classical registers"),
        Instruction("mz", [QubitId(0), RegisterId(0)], attributes=[Attribute("p1")]),
        Instruction("mz", [QubitId(1), RegisterId(1)], attributes=[Attribute("p1")]),
        Instruction("mz", [QubitId(2), RegisterId(2)], attributes=[Attribute("p2")]),
        Instruction("mz", [QubitId(3), RegisterId(3)], attributes=[Attribute("p2")]),
    ],
)

print(circuit)


# %%
import qstack

qvm = qstack.create_qvm("standard")

emulator = qvm.create_emulator()

emulator.eval(circuit, shots=10)

# %%
