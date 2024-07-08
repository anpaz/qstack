import numpy as np
from pyquil.gates import MEASURE
from pyquil.quil import DefGate

from qcir.circuit import Instruction, QubitId, RegisterId
from qstack import InstructionDefinition
from qstack.handler import Handler

from .context import Context


def _matrix_operation(inst: Instruction, qubits_count: int, context: Context):
    op_name = inst.name + "(" + ",".join([str(p) for p in inst.parameters]) + ")"
    if op_name not in context.constructors:
        matrix = np.array(inst.parameters).reshape(2**qubits_count, 2**qubits_count)
        gate_name = f"qstack__{len(context.constructors):010}"
        definition = DefGate(gate_name, matrix)
        ctx = definition.get_constructor()
        context.constructors[op_name] = ctx
        context.program += definition
    return context.constructors[op_name]


class Matrix1(Handler):
    @property
    def source(self):
        return InstructionDefinition(
            name="matrix1",
            # fmt: off
            parameters=[
                float, float,
                float, float,
            ],
            # fmt: on
            targets=[QubitId],
        )

    @property
    def uses(self):
        return None

    def handle(self, inst: Instruction, context: Context):
        op = _matrix_operation(inst, 1, context)
        context.program += op(inst.targets[0].value)


class Matrix2(Handler):
    @property
    def source(self):
        return InstructionDefinition(
            name="matrix2",
            # fmt: off
            parameters=[
                float, float, float, float,
                float, float, float, float,
                float, float, float, float,
                float, float, float, float,
            ],
            # fmt: on
            targets=[QubitId, QubitId],
        )

    @property
    def uses(self):
        return None

    def handle(self, inst: Instruction, context: Context):
        op = _matrix_operation(inst, 2, context)
        context.program += op(inst.targets[0].value, inst.targets[1].value)


class Measure(Handler):
    @property
    def source(self):
        return InstructionDefinition(
            name="measure",
            targets=[QubitId, RegisterId],
        )

    @property
    def uses(self):
        return None

    def handle(self, inst: Instruction, context: Context):
        context.program += MEASURE(inst.targets[0].value, context.readout[inst.targets[1].value])
