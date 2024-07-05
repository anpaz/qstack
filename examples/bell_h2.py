# %%
import math
import init_logging

init_logging.debug_qstack()

# %%
import math
from qcir import Circuit, Instruction, QubitId, Tick, Comment, RegisterId, Attribute

circuit = Circuit(
    name="prepare bell",
    instruction_set="h2",
    instructions=[
        Attribute("version", "1.0"),
        # Attribute("qubit_count", 4),
        # Attribute("register_count", 4),
        Tick(),
        Instruction("|0⟩", [QubitId(0)]),
        Instruction("|0⟩", [QubitId(1)]),
        Tick(),
        Comment("H 0"),
        Instruction("u1", parameters=[math.pi / 2.0, -math.pi / 2.0], targets=[QubitId(0)]),
        Instruction("rz", parameters=[math.pi], targets=[QubitId(0)]),
        Tick(),
        Comment("CX 0 1"),
        Instruction("u1", parameters=[-math.pi / 2.0, math.pi / 2.0], targets=[QubitId(1)]),
        Instruction("zz", [QubitId(0), QubitId(1)]),
        Instruction("rz", parameters=[-math.pi / 2.0], targets=[QubitId(0)]),
        Instruction("u1", parameters=[math.pi / 2.0, math.pi], targets=[QubitId(1)]),
        Instruction("rz", parameters=[-math.pi / 2.0], targets=[QubitId(1)]),
        Tick(),
        Instruction("mz", [QubitId(0), RegisterId(0)]),
        Instruction("mz", [QubitId(1), RegisterId(1)]),
    ],
)

print(circuit)


# %%
import qstack

emulator = qstack.create_stack("h2").create_emulator()
emulator.eval(circuit, shots=10)

# %%
from layers.h2 import U1, R

gate = U1()
print(gate.matrix(math.pi, 0) * 1j)
# %%
