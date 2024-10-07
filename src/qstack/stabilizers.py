from qcir.circuit import Circuit, Instruction, QubitId, RegisterId, Tick
from qstack.gadget import Gadget
from qstack.paulis import *
import qstack.layers.stabilizer.instruction_set as cliffords


class Context:
    def __init__(self, qubit_count: int, register_count: int):
        self.register_count = register_count
        self.qubit_count = qubit_count
        self.stabilizers = set()

    def new_register(self) -> RegisterId:
        result = RegisterId(self.register_count)
        self.register_count += 1
        return result

    def find_stabilizer_group(self, qubits: list[QubitId]) -> set[tuple[Pauli]]:
        result = set()
        for stabilizer in self.stabilizers:
            st = [stabilizer[q.value] for q in qubits]
            if any([p != I for p in st]):
                result.add(tuple(st))
        return result

    def add_stabilizer(self, stabilizer: list[Pauli], qubits: list[QubitId]):
        full_stabilizer = [I] * self.qubit_count
        for pauli, q in zip(stabilizer, qubits):
            full_stabilizer[q.value] = pauli
        self.stabilizers.add(tuple(full_stabilizer))

    def remove_stabilizer(self, stabilizer: list[Pauli], qubits: list[QubitId]):
        full_stabilizer = [I] * self.qubit_count
        for pauli, q in zip(stabilizer, qubits):
            full_stabilizer[q.value] = pauli
        self.stabilizers.remove(tuple(full_stabilizer))


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


def gadget_with_error_correction(name, instructions: list[Instruction], qubits: list[QubitId], context: Context):
    group = context.find_stabilizer_group(qubits)
    registers = [context.new_register() for i in range(len(group))]

    for register, stabilizer in zip(registers, group):
        instructions.append(Tick())
        instructions.append(cliffords.MeasurePauli(targets=([register] + qubits), parameters=stabilizer))

    decoder = build_stabilizer_decoder(qubits, registers, group)

    return Gadget(name, circuit=Circuit(instructions), decoder=decoder)
