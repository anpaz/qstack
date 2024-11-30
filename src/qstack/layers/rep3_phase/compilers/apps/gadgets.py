import logging
import qstack.layers.stabilizer.instruction_set as cliffords
from qstack.gadget import Gadget
from qstack.paulis import *
from qstack.circuit import Circuit, Instruction, QubitId, RegisterId, Tick
from qstack.stabilizers import Context as StabilizerContext, gadget_with_error_correction, update_syndrome_value

logger = logging.getLogger("qstack")


class Context(StabilizerContext):
    def __init__(self, qubit_count: int, register_count: int):
        super().__init__(qubit_count=qubit_count * 3, register_count=register_count, distance=1)
        self.blocks = {QubitId(i): [QubitId(i * 3 + d) for d in range(3)] for i in range(qubit_count)}


def prepare_zero(inst: Instruction, context: Context) -> Gadget:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    context.add_stabilizer([X, X, I], qubits)
    context.add_stabilizer([X, I, X], qubits)

    instructions = (
        [cliffords.PrepareZero(targets=[q], attributes=inst.attributes) for q in qubits]
        + [cliffords.H(targets=[q], attributes=inst.attributes) for q in qubits]
        + [
            cliffords.CX(targets=[qubits[0], qubits[1]]),
            cliffords.CX(targets=[qubits[0], qubits[2]]),
        ]
    )

    return gadget_with_error_correction("|0⟩", instructions, qubits, context)


def x(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    instructions = [cliffords.ApplyPauli(targets=qubits, parameters=[Z, Z, Z], attributes=inst.attributes)]

    return gadget_with_error_correction("x", instructions, qubits, context)


def h(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    # Instructions
    instructions = [
        cliffords.H(targets=[qubits[0]], attributes=inst.attributes),
        # cliffords.Z(targets=[qubits[0]], attributes=inst.attributes),
        cliffords.CZ(targets=[qubits[0], qubits[1]], attributes=inst.attributes),
        cliffords.CZ(targets=[qubits[0], qubits[2]], attributes=inst.attributes),
    ]

    # Update stabilizers
    group = context.find_stabilizer_group(qubits)
    for stabilizer in group:
        context.remove_stabilizer(stabilizer, qubits)
        stabilizer = by_h(stabilizer, 0)
        stabilizer = by_cz(stabilizer, 0, 1)
        stabilizer = by_cz(stabilizer, 0, 2)
        context.add_stabilizer(stabilizer, qubits)

    # swap qubit ids to keep instruction consistent.
    context.blocks[gadget_id] = [qubits[2], qubits[1], qubits[0]]

    return gadget_with_error_correction("h", instructions, qubits, context)


def cx(inst: Instruction, context: Context) -> Circuit:
    ctl_gadget_id = inst.targets[0]
    tgt_gadget_id = inst.targets[1]
    ctl_qubits = context.blocks[ctl_gadget_id]
    tgt_qubits = context.blocks[tgt_gadget_id]

    # Instructions
    instructions = [
        cliffords.CX(targets=[ctl_qubits[0], tgt_qubits[0]], attributes=inst.attributes),
        cliffords.CX(targets=[ctl_qubits[1], tgt_qubits[1]], attributes=inst.attributes),
        cliffords.CX(targets=[ctl_qubits[2], tgt_qubits[2]], attributes=inst.attributes),
    ]

    # update stabilizers:
    qubits = ctl_qubits + tgt_qubits
    group = context.find_stabilizer_group(qubits)
    for stabilizer in group:
        context.remove_stabilizer(stabilizer, qubits)
        stabilizer = by_cx(stabilizer, 0, 3)
        stabilizer = by_cx(stabilizer, 1, 4)
        stabilizer = by_cx(stabilizer, 2, 5)
        context.add_stabilizer(stabilizer, qubits)

    return gadget_with_error_correction("cx", instructions, qubits, context)


def measure_z(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[1]
    qubits = context.blocks[gadget_id]

    encoded_register = inst.targets[0]
    raw_register = context.new_register()

    instructions = [
        cliffords.MeasurePauli(
            targets=[raw_register] + qubits,
            parameters=[X, I, I],
            attributes=inst.attributes,
        ),
    ]

    def measure_decoder(memory: list[int], corrections):
        value = memory[raw_register.value]
        last_error = [corrections[q.value] for q in qubits]
        updated_value = update_syndrome_value(value, [X, I, I], last_error)

        memory[encoded_register.value] = updated_value

    return Gadget("⟨+z|", Circuit(instructions), decoder=measure_decoder)
