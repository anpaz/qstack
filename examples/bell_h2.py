# %%
import math
import init_logging

# %%
import math
from qcir import Circuit, Instruction, QubitId, Tick, Comment, RegisterId, Attribute

from qstack.layers.h2.instruction_set import U1, RZ, ZZ, Measure, PrepareZero


circuit = Circuit(
    name="prepare bell",
    instructions=[
        Attribute("version", "1.0"),
        # Attribute("qubit_count", 4),
        # Attribute("register_count", 4),
        Tick(),
        PrepareZero([QubitId(0)]),
        PrepareZero([QubitId(1)]),
        Tick(),
        Comment("H 0"),
        U1(parameters=[math.pi / 2.0, -math.pi / 2.0], targets=[QubitId(0)]),
        RZ(parameters=[math.pi], targets=[QubitId(0)]),
        Tick(),
        Comment("CX 0 1"),
        U1(parameters=[-math.pi / 2.0, math.pi / 2.0], targets=[QubitId(1)]),
        ZZ([QubitId(0), QubitId(1)]),
        RZ(parameters=[-math.pi / 2.0], targets=[QubitId(0)]),
        U1(parameters=[math.pi / 2.0, math.pi], targets=[QubitId(1)]),
        RZ(parameters=[-math.pi / 2.0], targets=[QubitId(1)]),
        Tick(),
        Measure([QubitId(0), RegisterId(0)]),
        Measure([QubitId(1), RegisterId(1)]),
    ],
)

print(circuit)


# %%
from compilers import StandardToMatrix, H2ToMatrix

compiler = H2ToMatrix()
target = compiler.compile(circuit)

print(target)

# %%
from qstack.emulators.pyQuil import Emulator

emulator = Emulator()
emulator.eval(target, shots=10)
# %%
