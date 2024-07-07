# %%
import init_logging

init_logging.debug_qstack()

# %%
from qcir import Circuit, Instruction, QubitId, Tick, Comment, RegisterId, Attribute

from instruction_sets.standard.instructions import MeasureZ, PrepareBell

circuit = Circuit(
    name="two bells",
    instructions=[
        Attribute("version", "1.0"),
        # Attribute("qubit_count", 4),
        # Attribute("register_count", 4000),
        Tick(),
        Comment("Prepare Bell Pairs"),
        PrepareBell([QubitId(0), QubitId(2)]),
        PrepareBell([QubitId(1), QubitId(3)]),
        Tick(),
        Comment("Measure qubits into classical registers"),
        MeasureZ([QubitId(0), RegisterId(0)], attributes=[Attribute("p1")]),
        MeasureZ([QubitId(1), RegisterId(1)], attributes=[Attribute("p2")]),
        MeasureZ([QubitId(2), RegisterId(2)], attributes=[Attribute("p1")]),
        MeasureZ([QubitId(3), RegisterId(3)], attributes=[Attribute("p2")]),
    ],
)

print(circuit)


# %%
from compilers import StandardToMatrix

compiler = StandardToMatrix()
target = compiler.compile(circuit)

print(target)

# %%
from qstack.emulators.pyQuil import Emulator

emulator = Emulator()
emulator.eval(target, shots=10)

# emulator = qstack.create_stack("standard").create_emulator()
# emulator.eval(circuit, shots=10)

# %%
