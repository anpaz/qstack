from qcir.circuit import Instruction
from .context import Context


def handle_prepare(inst: Instruction, context: Context):
    pass


def handle_1qubit(inst: Instruction, context: Context):
    context.circuit.append(inst.name, inst.targets[0].value)


def handle_2qubit(inst: Instruction, context: Context):
    context.circuit.append(inst.name, [inst.targets[0].value, inst.targets[1].value])


def handle_measure(inst: Instruction, context: Context):
    context.circuit.append("MZ", inst.targets[1].value)
    context.measurements_map[inst.targets[0].value] = context.measurements_count
    context.measurements_count += 1


def handle_apply_pauli(inst: Instruction, context: Context):
    for basis, target in zip(inst.parameters, inst.targets):
        context.circuit.append(basis, target.value)


def handle_measure_pauli(inst: Instruction, context: Context):
    import stim

    def select_target(basis):
        if basis == "X":
            return stim.target_x
        elif basis == "Y":
            return stim.target_y
        elif basis == "Z":
            return stim.target_z
        else:
            assert False, f"Invalid Pauli basis: {basis}"

    pauli = stim.target_combined_paulis(
        [select_target(basis)(target.value) for (basis, target) in zip(inst.parameters, inst.targets[1:])]
    )
    context.circuit.append("mpp", pauli)
    context.measurements_map[inst.targets[0].value] = context.measurements_count
    context.measurements_count += 1
