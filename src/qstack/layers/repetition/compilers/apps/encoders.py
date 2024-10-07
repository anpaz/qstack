import logging

import qstack.layers.stabilizer.instruction_set as cliffords

from qcir.circuit import Circuit, Comment, Instruction, QubitId, RegisterId, Tick
from qstack.gadget import Gadget, QuantumKernel

from qstack.paulis import *


logger = logging.getLogger("qstack")


class Context:
    def __init__(self, kernel: QuantumKernel):
        # def base_decoder(memory: list[int], corrections):
        #     return tuple(kernel.decoder(memory[: kernel.register_count]))

        self.blocks = {
            QubitId(i): [QubitId(i * 3), QubitId(i * 3 + 1), QubitId(i * 3 + 2)] for i in range(kernel.qubit_count)
        }

        self.next_measurement = kernel.register_count
        self.stabilizers = set()


def decode_syndrome(syndrome):
    if syndrome == [0, 0]:
        return [I, I, I]

    if syndrome == [1, 0]:
        return [I, X, I]

    if syndrome == [0, 1]:
        return [I, I, X]

    if syndrome == [1, 1]:
        return [X, I, I]


def update_syndrome_value(value: int, syndrome: list[Pauli], correction: list[Pauli]):
    for s, c in zip(syndrome, correction):
        if s == c or c == I or s == I:
            pass
        else:
            value += 1 + (s.sign // 2) + (c.sign // 2)
    return value % 2


# def conjugate_by_h(stabilizers: list[list[str]]):
#     def conjugate_one(st):
#         def conjugate_one_basis(s):
#             if s == "X":
#                 return "Z"
#             if s == "Z":
#                 return "X"
#             if s == "I":
#                 return "I"
#             assert False, "Unexpected basis"

#         return [conjugate_one_basis(s) for s in st]

#     return [conjugate_one(st) for st in stabilizers]


# def conjugate_by_cx(all_control: list[list[str]], all_target: list[list[str]]):
#     assert all_control[0][0] == "Y"
#     assert all_target[1][0] == "Z"

#     all_control[0] = ["Y", "Y", "X"]
#     all_control[1] = ["Y", "X", "Y"]
#     all_control.append(["Z", "Z", "I"])
#     all_control.append(["Z", "I", "Z"])

#     all_target[0] = ["Z", "Z", "I"]
#     all_target[1] = ["Z", "I", "Z"]
#     all_target.append(["X", "X", "X"])

#     # for st_control, st_target in zip(all_control, all_target):
#     #     assert len(st_control) == len(st_target)
#     #     for i in range(len(st_control)):
#     #         c, t = st_control[i], st_target[i]
#     #         if c == "X":
#     #             if t == "I":
#     #                 st_target[i] = "X"
#     #             elif t == "X":
#     #                 st_target[i] = "I"
#     #             elif t == "Z":
#     #                 st_target[i] = "X"
#     #             else:
#     #                 assert False, f"Unexpected target basis {t}"

#     #         elif t == "Z":
#     #             if c == "Z":
#     #                 st_target[i] = "I"
#     #             elif c == "I":
#     #                 st_target[i] = "Z"
#     #             if c == "X":
#     #                 st_target[i] = "Z"
#     #             else:
#     #                 assert False, f"Unexpected control basis: {c}"


# def multiply(left, right):
#     def check_one(l, r):
#         if l == "I":
#             return r
#         if r == "I":
#             return l
#         if l == r:
#             return "I"
#         assert False, f"Unexpected: {l}, {r}"

#     result = [check_one(l, r) for l, r in zip(left, right)]
#     return result


# %%
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

    def decoder(memory: list[int], corrections: list[Pauli]):
        last_error = [corrections[q.value] for q in qubits]
        syndrome = [memory[r.value] for r in registers]

        new_syndrome = tuple([update_syndrome_value(v, s, last_error) for (v, s) in zip(syndrome, group)])
        if new_syndrome in lookup_table:
            new_correction = lookup_table[new_syndrome]
        else:
            new_correction = [I] * len(qubits)

        for i, q in enumerate(qubits):
            corrections[q.value] = last_error[i] * new_correction[i]

    return decoder


# qubits = [QubitId(3), QubitId(4), QubitId(5)]
# stabilizers = [
#     [I, I, I, Z, Z, I],
#     [I, I, I, Z, I, Z],
#     [X, X, I, I, I, I],
#     [X, I, X, I, I, I],
# ]

# group = find_stabilizer_group(qubits, stabilizers)
# registers = [RegisterId(0), RegisterId(1)]

# decoder = build_stabilizer_decoder(qubits, registers, group)

# memory = [0, 1, 0, 0]
# correction = [I, I, I, I, I, I]

# decoder(memory, correction)
# correction


# %%

# def syndrome_extraction(block: QubitId, context: Context):
#     targets = context.blocks[block]
#     registers = [RegisterId(i + context.next_measurement) for i in range(len(context.stabilizer[block]))]

#     inst = [
#         cliffords.MeasurePauli(targets=([r] + targets), parameters=s)
#         for r, s in zip(registers, [str(abs(op)) for op in context.stabilizer[block]])
#     ]

#     decoder = build_decoder(block, registers, context.stabilizer[block])

#     context.next_measurement += len(context.stabilizer[block])
#     context.decoders.append(decoder)

#     return inst


def with_error_correction(instructions: list[Instruction], qubits: list[QubitId], context: Context):
    group = find_stabilizer_group(qubits, context.stabilizer)
    registers = [RegisterId(i + context.next_measurement) for i in range(len(group))]

    instructions += [
        Tick(),
    ]
    # Syndrome extraction:
    instructions += [
        cliffords.MeasurePauli(targets=([r] + qubits), parameters=s)
        for r, s in zip(registers, [str(abs(op)) for op in group])
    ]

    decoder = build_stabilizer_decoder(qubits, registers, group)
    return instructions, decoder


def prepare_zero(inst: Instruction, context: Context) -> Gadget:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    instructions, decoder = with_error_correction(
        [cliffords.PrepareZero(targets=[q], attributes=inst.attributes) for q in qubits]
    )

    return Gadget("|0⟩", instructions=instructions, decoder=decoder)


def x(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    instructions, decoder = with_error_correction(
        [cliffords.ApplyPauli(targets=qubits, parameters=["X", "X", "X"], attributes=inst.attributes)]
    )

    return Gadget("x", instructions=instructions, decoder=decoder)


def h(inst: Instruction, context: Context) -> Circuit:
    gadget_id = inst.targets[0]
    qubits = context.blocks[gadget_id]

    instructions = [
        cliffords.H(targets=[qubits[0]], attributes=inst.attributes),
        cliffords.CX(targets=[qubits[0], qubits[1]], attributes=inst.attributes),
        cliffords.CX(targets=[qubits[0], qubits[2]], attributes=inst.attributes),
    ]

    by_h(context.stabilizers, qubits[0])
    by_cx(context.stabilizers, qubits[0], qubits[1])
    by_cx(context.stabilizers, qubits[0], qubits[2])

    instructions, decoder = with_error_correction(
        [cliffords.ApplyPauli(targets=qubits, parameters=["X", "X", "X"], attributes=inst.attributes)]
    )

    return Gadget("x", instructions=instructions, decoder=decoder)


def cx(inst: Instruction, context: Context) -> Circuit:
    ctl = inst.targets[0]
    tgt = inst.targets[1]
    controls = context.blocks[ctl]
    targets = context.blocks[tgt]
    inst = [
        cliffords.CX(targets=[controls[0], targets[0]], attributes=inst.attributes),
        cliffords.CX(targets=[controls[1], targets[1]], attributes=inst.attributes),
        cliffords.CX(targets=[controls[2], targets[2]], attributes=inst.attributes),
        # cliffords.X(targets=[controls[0]], attributes=inst.attributes),
    ]

    # Syndrome extraction
    ctl_registers = [RegisterId(i + context.next_measurement) for i in range(len(context.stabilizer[ctl]))]
    tgt_registers = [
        RegisterId(i + context.next_measurement + len(context.stabilizer[ctl]))
        for i in range(len(context.stabilizer[tgt]))
    ]

    logger.debug(f"stabilizers before {context.stabilizer[ctl]}, {context.stabilizer[tgt]}")
    # conjugate_by_cx(context.stabilizer[ctl], context.stabilizer[tgt])

    stabilizers = [
        ["Z", "Z", "I", "Z", "Z", "I"],
        ["Z", "I", "Z", "Z", "I", "Z"],
        ["Y", "Y", "X", "X", "X", "X"],
        ["Y", "X", "Y", "X", "X", "X"],
    ]

    # all_control.append(["Z", "Z", "I"])
    # all_control.append(["Z", "I", "Z"])

    # all_target[0] = ["Z", "Z", "I"]
    # all_target[1] = ["Z", "I", "Z"]
    # all_target.append(["X", "X", "X"])

    logger.debug(f"stabilizers after {context.stabilizer[ctl]}, {context.stabilizer[tgt]}")

    syndrome_extraction = [
        cliffords.MeasurePauli(targets=([r] + controls + targets), parameters=s)
        for r, s in zip((ctl_registers + tgt_registers), stabilizers)
        # ] + [
        #     cliffords.MeasurePauli(targets=([r] + targets), parameters=s)
        #     for r, s in zip(tgt_registers, context.stabilizer[tgt])
    ]

    ctl_stabilizer = context.stabilizer[ctl]
    tgt_stabilizer = context.stabilizer[tgt]

    def decoder(memory: list[int], corrections):
        ctl_last_correction = corrections[ctl]
        tgt_last_correction = corrections[tgt]

        ctl_syndrome = [memory[r.value] for r in ctl_registers]
        tgt_syndrome = [memory[r.value] for r in tgt_registers]

        ctl_inherited_correction = []
        for b in tgt_last_correction:
            if b == "Z":
                ctl_inherited_correction.append("Z")
            else:
                ctl_inherited_correction.append("I")
        ctl_correction = multiply(ctl_last_correction, ctl_inherited_correction)

        tgt_inherited_correction = []
        for b in ctl_last_correction:
            if b == "X":
                tgt_inherited_correction.append("X")
            else:
                tgt_inherited_correction.append("I")
        tgt_correction = multiply(tgt_last_correction, tgt_inherited_correction)

        new_ctl_syndrome = [
            update_syndrome_value(v, s, ctl_correction) for (v, s) in zip(ctl_syndrome, ctl_stabilizer)
        ]
        new_tgt_syndrome = [
            update_syndrome_value(v, s, tgt_correction) for (v, s) in zip(tgt_syndrome, tgt_stabilizer)
        ]

        new_ctl_correction = decode_syndrome(new_ctl_syndrome)
        new_tgt_correction = decode_syndrome(new_tgt_syndrome)

        corrections[ctl] = multiply(ctl_correction, new_ctl_correction)
        corrections[tgt] = multiply(tgt_correction, new_tgt_correction)

    context.next_measurement += len(context.stabilizer[ctl]) + len(context.stabilizer[tgt])
    # return Circuit("encode:cx", inst)

    # context.decoders.append(decoder)
    return Circuit("encode:cx", inst + syndrome_extraction)


def measure(inst: Instruction, context: Context) -> Circuit:
    targets = context.blocks[inst.targets[1]]
    register = context.next_measurement
    result = [
        cliffords.MeasurePauli(
            targets=[RegisterId(register)] + targets,
            parameters=context.z_op,
            attributes=inst.attributes,
        )
    ]

    def decoder(memory: list[int], corrections):
        value = memory[register]
        last_correction = corrections[inst.targets[1]]
        updated_value = update_syndrome_value(value, context.z_op, last_correction)

        memory[inst.targets[0].value] = updated_value

    context.next_measurement += 1
    context.decoders.append(decoder)

    return Circuit("encode:mz", result)
