import logging
import qstack.layers.stabilizer.instruction_set as cliffords
from qstack.gadget import Gadget
from qstack.paulis import *
from qcir.circuit import Circuit, Instruction, QubitId, RegisterId, Tick

logger = logging.getLogger("qstack")


class Context:
    def __init__(self, qubit_count: int, register_count: int):
        self.blocks = {
            QubitId(i): [QubitId(i * 3), QubitId(i * 3 + 1), QubitId(i * 3 + 2)] for i in range(qubit_count)
        }
        self.next_measurement = register_count
        self.stabilizers = set()


def build_error_lookup(stabilizers: set[list[Pauli]]):
    if not stabilizers:
        return {}
    n = len(list(stabilizers)[0])
    table = {}
    for p in [Y, Z, X, I]:
        for i in range(n):

            def eval_one(stabilizer: list[Pauli], error: list[Pauli]):
                value = 0
                for s, e in zip(stabilizer, error):
                    if not commutes(s, e):
                        value += 1
                return value % 2

            error = [I] * n
            error[i] = p
            syndrome = tuple([eval_one(s, error) for s in stabilizers])
            table[syndrome] = error
    return table


def find_stabilizer_group(qubits: list[QubitId], stabilizers: list[Pauli]) -> set[tuple[Pauli]]:
    result = set()
    for stabilizer in stabilizers:
        st = [stabilizer[q.value] for q in qubits]
        if any([p != I for p in st]):
            result.add(tuple(st))
    return result


def update_syndrome_value(value: int, syndrome: list[Pauli], error: list[Pauli]):
    for s, e in zip(syndrome, error):
        if not commutes(s, e):
            value += 1 + (s.sign // 2) + (e.sign // 2)
    return value % 2


def build_stabilizer_decoder(qubits: list[QubitId], registers: list[RegisterId], group: set[tuple[Pauli]]):
    lookup_table = build_error_lookup(group)

    def stabilizer_decoder(memory: list[int], corrections: list[Pauli]):
        last_error = [corrections[q.value] for q in qubits]
        syndrome = [memory[r.value] for r in registers]

        new_syndrome = tuple([update_syndrome_value(v, s, last_error) for (v, s) in zip(syndrome, group)])
        if new_syndrome in lookup_table:
            new_correction = lookup_table[new_syndrome]
        else:
            new_correction = [I] * len(qubits)

        for i, q in enumerate(qubits):
            corrections[q.value] = last_error[i] * new_correction[i]

    return stabilizer_decoder


def add_stabilizer(stabilizer: list[Pauli], qubits: list[QubitId], context: Context):
    full_stabilizer = [I] * len(context.blocks.keys()) * 3
    for pauli, q in zip(stabilizer, qubits):
        full_stabilizer[q.value] = pauli
    context.stabilizers.add(tuple(full_stabilizer))


def remove_stabilizer(stabilizer: list[Pauli], qubits: list[QubitId], context: Context):
    full_stabilizer = [I] * len(context.blocks.keys()) * 3
    for pauli, q in zip(stabilizer, qubits):
        full_stabilizer[q.value] = pauli
    context.stabilizers.remove(tuple(full_stabilizer))


def gadget_with_error_correction(name, instructions: list[Instruction], qubits: list[QubitId], context: Context):
    group = find_stabilizer_group(qubits, context.stabilizers)
    registers = [RegisterId(i + context.next_measurement) for i in range(len(group))]

    for register, stabilizer in zip(registers, group):
        instructions.append(Tick())
        instructions.append(cliffords.MeasurePauli(targets=([register] + qubits), parameters=stabilizer))

    decoder = build_stabilizer_decoder(qubits, registers, group)
    context.next_measurement += len(registers)

    return Gadget(name, circuit=Circuit(instructions), decoder=decoder)


def prepare_zero(inst: Instruction, context: Context) -> Gadget:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    add_stabilizer([Z, Z, I], qubits, context)
    add_stabilizer([Z, I, Z], qubits, context)

    instructions = [cliffords.PrepareZero(targets=[q], attributes=inst.attributes) for q in qubits]

    return gadget_with_error_correction("|0⟩", instructions, qubits, context)


def x(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    instructions = [cliffords.ApplyPauli(targets=qubits, parameters=[X, X, X], attributes=inst.attributes)]

    return gadget_with_error_correction("x", instructions, qubits, context)


def h(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    # Instructions
    instructions = [
        cliffords.H(targets=[qubits[0]], attributes=inst.attributes),
        cliffords.Z(targets=[qubits[0]], attributes=inst.attributes),
        cliffords.CX(targets=[qubits[0], qubits[1]], attributes=inst.attributes),
        cliffords.CX(targets=[qubits[0], qubits[2]], attributes=inst.attributes),
    ]

    # Update stabilizers
    group = find_stabilizer_group(qubits, context.stabilizers)
    for stabilizer in group:
        remove_stabilizer(stabilizer, qubits, context)
        stabilizer = by_h(stabilizer, 0)
        stabilizer = by_cx(stabilizer, 0, 1)
        stabilizer = by_cx(stabilizer, 0, 2)
        add_stabilizer(stabilizer, qubits, context)

    # swap qubit ids to keep instruction consistent.
    context.blocks[gadget_id] = [qubits[2], qubits[1], qubits[0]]

    return gadget_with_error_correction("x", instructions, qubits, context)


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
    group = find_stabilizer_group(qubits, context.stabilizers)
    for stabilizer in group:
        remove_stabilizer(stabilizer, qubits, context)
        stabilizer = by_cx(stabilizer, 0, 3)
        stabilizer = by_cx(stabilizer, 1, 4)
        stabilizer = by_cx(stabilizer, 2, 5)
        add_stabilizer(stabilizer, qubits, context)

    return gadget_with_error_correction("x", instructions, qubits, context)


def measure_z(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[1]
    qubits = context.blocks[gadget_id]

    register_id = inst.targets[0]
    register = context.next_measurement

    instructions = [
        cliffords.MeasurePauli(
            targets=[RegisterId(register)] + qubits,
            parameters=[Z, I, I],
            attributes=inst.attributes,
        ),
    ]

    def measure_decoder(memory: list[int], corrections):
        value = memory[register]
        last_error = [corrections[q.value] for q in qubits]
        updated_value = update_syndrome_value(value, [Z, I, I], last_error)

        memory[register_id.value] = updated_value

    context.next_measurement += 1

    return Gadget("⟨+z|", Circuit(instructions), decoder=measure_decoder)
