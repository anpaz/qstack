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


def handle_matrix1(inst: Instruction, context: Context):
    op = _matrix_operation(inst, 1, context)
    context.program += op(inst.targets[0].value)


def handle_matrix2(inst: Instruction, context: Context):
    op = _matrix_operation(inst, 2, context)
    context.program += op(inst.targets[0].value, inst.targets[1].value)


def handle_measure(inst: Instruction, context: Context):
    context.program += MEASURE(inst.targets[0].value, context.readout[inst.targets[1].value])
