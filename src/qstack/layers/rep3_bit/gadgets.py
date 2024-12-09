import logging
from qstack.gadget import Gadget, Instruction, QubitId, GadgetContext
from qstack.paulis import *
from qstack.stabilizers import SyndromExtraction, update_syndrome_bit, stabilizer_for

logger = logging.getLogger("qstack")


def PrepareZero(target) -> Gadget:
    target = QubitId.wrap(target)
    qubits = [QubitId(f"{target.value}.{idx}") for idx in range(3)]

    prep = Gadget(name="|0⟩", prepare=[Instruction(name="|0⟩", targets=[q]) for q in qubits])
    return prep


def X(target) -> Gadget:
    target = QubitId.wrap(target)
    qubits = [QubitId(f"{target.value}.{idx}") for idx in range(3)]
    stabilizers = [
        stabilizer_for([Z, Z, I], qubits),
        stabilizer_for([Z, I, Z], qubits),
    ]

    compute = Gadget(name="x", compute=[Instruction(name="x", targets=[q]) for q in qubits])
    correct = SyndromExtraction(qubits=qubits, stabilizers=stabilizers)
    return compute | correct


def MeasureZ(target) -> Gadget:
    target = QubitId.wrap(target)
    qubits = [QubitId(f"{target.value}.{idx}") for idx in range(3)]

    def measure_decoder(bits: tuple[int], context):
        corrections = context.get("corrections", {})
        last_error = {q: corrections.get(q, I) for q in qubits}
        # if any([c == None for c in last_error]):
        #     memory[encoded_register.value] = "?"
        # else:z
        stabilizer = stabilizer_for([Z, I, I], qubits)
        updated_value = update_syndrome_bit(bits[0], stabilizer, last_error)

        return (updated_value,), context

    return Gadget(name="mz", measure=[Instruction(name="mz", targets=[q]) for q in qubits], decode=measure_decoder)


# def x(inst: Instruction, context: Context) -> Circuit:
#     gadget_id = inst.targets[0]
#     qubits = context.blocks[gadget_id]

#     instructions = [cliffords.ApplyPauli(targets=qubits, parameters=[X, X, X], attributes=inst.attributes)]

#     return gadget_with_error_correction("x", instructions, qubits, context)


# def h(inst: Instruction, context: Context) -> Circuit:
#     gadget_id = inst.targets[0]
#     qubits = context.blocks[gadget_id]

#     # Instructions
#     instructions = [cliffords.H(targets=[q], attributes=inst.attributes) for q in qubits]

#     # # swap qubit ids to keep instruction consistent.
#     # context.blocks[gadget_id] = [qubits[2], qubits[1], qubits[0]]

#     return gadget_with_error_correction("h", instructions, qubits, context, abort=True)


# def cx(inst: Instruction, context: Context) -> Circuit:
#     ctl_gadget_id = inst.targets[0]
#     tgt_gadget_id = inst.targets[1]
#     ctl_qubits = context.blocks[ctl_gadget_id]
#     tgt_qubits = context.blocks[tgt_gadget_id]

#     # Instructions
#     instructions = [
#         cliffords.CX(targets=[ctl_qubits[0], tgt_qubits[0]], attributes=inst.attributes),
#         cliffords.CX(targets=[ctl_qubits[1], tgt_qubits[1]], attributes=inst.attributes),
#         cliffords.CX(targets=[ctl_qubits[2], tgt_qubits[2]], attributes=inst.attributes),
#     ]

#     qubits = ctl_qubits + tgt_qubits

#     return gadget_with_error_correction("cx", instructions, qubits, context)


# def measure_z(inst: Instruction, context: Context) -> Circuit:
#     gadget_id = inst.targets[1]
#     qubits = context.blocks[gadget_id]

#     encoded_register = inst.targets[0]
#     raw_register = context.new_register()

#     instructions = [
#         cliffords.MeasureZ(
#             targets=[raw_register, qubits[0]],
#             attributes=inst.attributes,
#         ),
#     ]

#     def measure_decoder(memory: list[int], corrections):
#         value = memory[raw_register.value]
#         last_error = [corrections[q.value] for q in qubits]
#         if any([c == None for c in last_error]):
#             memory[encoded_register.value] = "?"
#         else:
#             updated_value = update_syndrome_value(value, [Z, I, I], last_error)
#             memory[encoded_register.value] = updated_value

#     return Gadget("⟨+z|", Circuit(instructions), decoder=measure_decoder)
