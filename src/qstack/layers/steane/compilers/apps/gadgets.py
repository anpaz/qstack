import logging
import qstack.layers.stabilizer.instruction_set as cliffords
from qstack.gadget import Gadget
from qstack.paulis import *
from qcir.circuit import Circuit, Instruction, QubitId, RegisterId, Tick
from qstack.stabilizers import Context as StabilizerContext, gadget_with_error_correction, update_syndrome_value

logger = logging.getLogger("qstack")


class Context(StabilizerContext):
    def __init__(self, qubit_count: int, register_count: int):
        d = 7
        super().__init__(qubit_count=qubit_count * d, register_count=register_count)
        self.blocks = {}
        for i in range(qubit_count):
            self.blocks[QubitId(i)] = [QubitId(i * d + j) for j in range(d)]


def prepare_zero(inst: Instruction, context: Context) -> Gadget:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    # context.add_stabilizer([I, I, I, X, X, X, X], qubits)
    # context.add_stabilizer([I, X, X, I, I, X, X], qubits)
    # context.add_stabilizer([X, I, X, I, X, I, X], qubits)
    # context.add_stabilizer([I, I, I, Z, Z, Z, Z], qubits)
    # context.add_stabilizer([I, Z, Z, I, I, Z, Z], qubits)
    # context.add_stabilizer([Z, I, Z, I, Z, I, Z], qubits)
    context.add_stabilizer([X, I, I, X, X, X, I], qubits)
    context.add_stabilizer([I, X, I, X, I, X, X], qubits)
    context.add_stabilizer([I, I, X, I, X, X, X], qubits)
    context.add_stabilizer([Z, I, I, Z, Z, Z, I], qubits)
    context.add_stabilizer([I, Z, I, Z, I, Z, Z], qubits)
    context.add_stabilizer([I, I, Z, I, Z, Z, Z], qubits)

    instructions = [cliffords.PrepareZero(targets=[q], attributes=inst.attributes) for q in qubits]

    # taken from: https://arxiv.org/pdf/2309.11793 page 12
    instructions += [
        cliffords.H(targets=[qubits[0]]),
        cliffords.H(targets=[qubits[1]]),
        cliffords.H(targets=[qubits[2]]),
        cliffords.CX(targets=[qubits[6], qubits[3]]),
        cliffords.CX(targets=[qubits[6], qubits[4]]),
        cliffords.CX(targets=[qubits[0], qubits[3]]),
        cliffords.CX(targets=[qubits[0], qubits[4]]),
        cliffords.CX(targets=[qubits[0], qubits[5]]),
        cliffords.CX(targets=[qubits[1], qubits[3]]),
        cliffords.CX(targets=[qubits[1], qubits[5]]),
        cliffords.CX(targets=[qubits[1], qubits[6]]),
        cliffords.CX(targets=[qubits[2], qubits[4]]),
        cliffords.CX(targets=[qubits[2], qubits[5]]),
        cliffords.CX(targets=[qubits[2], qubits[6]]),
    ]

    return gadget_with_error_correction("|0⟩", instructions, qubits, context)


def x(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    instructions = [
        cliffords.X(targets=[qubits[3]]),
        cliffords.X(targets=[qubits[4]]),
        cliffords.X(targets=[qubits[6]]),
    ]

    return gadget_with_error_correction("x", instructions, qubits, context)


def h(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    # Instructions
    instructions = [cliffords.H(targets=[qubits[i]], attributes=inst.attributes) for i in range(7)]

    return gadget_with_error_correction("h", instructions, qubits, context)


def cx(inst: Instruction, context: Context) -> Circuit:
    ctl_gadget_id = inst.targets[0]
    tgt_gadget_id = inst.targets[1]
    ctl_qubits = context.blocks[ctl_gadget_id]
    tgt_qubits = context.blocks[tgt_gadget_id]
    qubits = ctl_qubits + tgt_qubits

    # Instructions
    instructions = [cliffords.CX(targets=[ctl_qubits[i], tgt_qubits[i]], attributes=inst.attributes) for i in range(7)]

    # update stabilizers:
    qubits = ctl_qubits + tgt_qubits
    group = context.find_stabilizer_group(qubits)
    for stabilizer in group:
        context.remove_stabilizer(stabilizer, qubits)
        for i in range(7):
            stabilizer = by_cx(stabilizer, i, i + 7)
        context.add_stabilizer(stabilizer, qubits)

    return gadget_with_error_correction("cx", instructions, qubits, context)


def measure_z(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[1]
    qubits = context.blocks[gadget_id]

    encoded_register = inst.targets[0]
    raw_register = context.new_register()

    z_op = [I, Z, Z, I, I, I, Z]

    instructions = [
        cliffords.MeasurePauli(
            targets=[raw_register] + qubits,
            parameters=z_op,
            attributes=inst.attributes,
        ),
    ]

    def measure_decoder(memory: list[int], corrections):
        value = memory[raw_register.value]
        last_error = [corrections[q.value] for q in qubits]
        updated_value = update_syndrome_value(value, z_op, last_error)

        memory[encoded_register.value] = updated_value

    return Gadget("⟨+z|", Circuit(instructions), decoder=measure_decoder)
