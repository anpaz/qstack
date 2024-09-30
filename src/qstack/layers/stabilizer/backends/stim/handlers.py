from qcir.circuit import Instruction
from .context import Context


def handle_prepare(inst: Instruction, context: Context):
    pass


def handle_1qubit(inst: Instruction, context: Context):
    if context.noise_1qubit_gate is not None:
        context.circuit.append("DEPOLARIZE1", targets=inst.targets[0].value, arg=context.noise_1qubit_gate)
    context.circuit.append(inst.name, inst.targets[0].value)


def handle_2qubit(inst: Instruction, context: Context):
    if context.noise_1qubit_gate is not None:
        context.circuit.append(
            "DEPOLARIZE2", [inst.targets[0].value, inst.targets[1].value], context.noise_2qubit_gate
        )
    context.circuit.append(inst.name, [inst.targets[0].value, inst.targets[1].value])


def handle_measure(inst: Instruction, context: Context):
    if context.noise_measure is not None:
        context.circuit.append("X_ERROR", [inst.targets[1].value], arg=context.noise_measure)
    context.circuit.append("MZ", inst.targets[1].value)
    context.measurements_map[inst.targets[0].value] = context.measurements_count
    context.measurements_count += 1


def handle_apply_pauli(inst: Instruction, context: Context):
    for basis, target in zip(inst.parameters, inst.targets):
        if context.noise_1qubit_gate is not None:
            context.circuit.append("DEPOLARIZE1", targets=target.value, arg=context.noise_1qubit_gate)
        context.circuit.append(basis, target.value)


def handle_measure_pauli(inst: Instruction, context: Context):
    import stim

    def select_noise(basis):
        if basis == "X":
            return stim.target_z
        elif basis == "Y":
            return stim.target_z
        elif basis == "Z":
            return stim.target_x
        else:
            assert False, f"Invalid Pauli basis: {basis}"

    def select_target(basis):
        if basis == "X":
            return stim.target_x
        elif basis == "Y":
            return stim.target_y
        elif basis == "Z":
            return stim.target_z
        else:
            assert False, f"Invalid Pauli basis: {basis}"

    if context.noise_measure is not None:
        for basis, target in zip(inst.parameters, inst.targets[1:]):
            if basis == "Z":
                context.circuit.append("X_ERROR", [target.value], arg=context.noise_measure)
            elif basis == "X":
                context.circuit.append("Z_ERROR", [target.value], arg=context.noise_measure)
            elif basis == "Y":
                context.circuit.append("X_ERROR", [target.value], arg=context.noise_measure)
                context.circuit.append("Z_ERROR", [target.value], arg=context.noise_measure)

    pauli = stim.target_combined_paulis(
        [
            select_target(basis)(target.value)
            for (basis, target) in zip(inst.parameters, inst.targets[1:])
            if basis != "I"
        ]
    )
    context.circuit.append("mpp", pauli)
    context.measurements_map[inst.targets[0].value] = context.measurements_count
    context.measurements_count += 1
