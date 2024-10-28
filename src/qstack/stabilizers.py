# %%
from qcir.circuit import Circuit, Instruction, QubitId, RegisterId, Tick
from qstack.gadget import Gadget
from qstack.paulis import *
import qstack.layers.stabilizer.instruction_set as cliffords

import logging

logger = logging.getLogger("qstack")


def build_lookup_table(stabilizers: set[tuple[Pauli]], distance: int):
    if not stabilizers:
        return {}

    n = len(list(stabilizers)[0])

    def eval(stabilizer: list[Pauli], error: list[Pauli]):
        value = 0
        for s, e in zip(stabilizer, error):
            if not commutes(s, e):
                value += 1
        return value % 2

    def find_syndromes(error, table, d):
        if d == 0:
            return
        for i in range(n):
            if not error[i] == I:
                continue
            for e in [X, Z]:
                error[i] = e
                syndrome = tuple([eval(s, error) for s in stabilizers])
                if syndrome == trivial:
                    logger.debug(f"trivial syndrome: {error}")
                elif syndrome in table:
                    if not error == table[syndrome]:
                        logger.debug(f"conflict for {syndrome}: {error}--{table[syndrome]}")
                else:
                    table[syndrome] = error.copy()
                find_syndromes(error, table, d - 1)
            error[i] = I

    table = {}
    error = [I] * n
    trivial = tuple([0] * len(stabilizers))
    table[trivial] = error
    find_syndromes(error, table, distance)
    return table


stabilizers = [
    [I, I, I, X, X, X, X],
    [I, X, X, I, I, X, X],
    [X, I, X, I, X, I, X],
    [I, I, I, Z, Z, Z, Z],
    [I, Z, Z, I, I, Z, Z],
    [Z, I, Z, I, Z, I, Z],
]
stabilizers = {tuple(s) for s in stabilizers}

table = build_lookup_table(stabilizers, 3)
table


# %%
def update_syndrome_value(value: int, syndrome: list[Pauli], error: list[Pauli]):
    for s, e in zip(syndrome, error):
        if not commutes(s, e):
            value += 1 + (s.sign // 2) + (e.sign // 2)
    return value % 2


class Context:

    def __init__(self, qubit_count: int, register_count: int, distance: int):
        self.register_count = register_count
        self.qubit_count = qubit_count
        self.stabilizers = set()
        self.distance = distance
        self.tables = {}

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

    def build_decoder(self, qubits: list[QubitId], registers: list[RegisterId], abort: bool):
        group = self.find_stabilizer_group(qubits)

        key = tuple([s for s in group])
        if key not in self.tables:
            self.tables[key] = build_lookup_table(group, self.distance)
        lookup_table = self.tables[key]

        def stabilizer_decoder(memory: list[int], corrections: list[Pauli]):
            last_error = [corrections[q.value] for q in qubits]
            # if any of the qubits are aborted, abort the entire decoding
            if any([c == None for c in last_error]):
                for i, q in enumerate(qubits):
                    corrections[q.value] = None
                return

            syndrome = [memory[r.value] for r in registers]
            new_syndrome = tuple([update_syndrome_value(v, s, last_error) for (v, s) in zip(syndrome, group)])

            if abort:
                trivial_syndrome = tuple([0] * len(registers))
                if new_syndrome == trivial_syndrome:
                    return
                else:
                    for i, q in enumerate(qubits):
                        corrections[q.value] = None
                    return

            if new_syndrome in lookup_table:
                new_correction = lookup_table[new_syndrome]
            else:
                logger.warning(f"Syndrome {new_syndrome} not found in correction table.")
                new_correction = [I] * len(qubits)

            for i, q in enumerate(qubits):
                corrections[q.value] = last_error[i] * new_correction[i]

        return stabilizer_decoder


def gadget_with_error_correction(
    name, instructions: list[Instruction], qubits: list[QubitId], context: Context, abort: bool = False
):
    group = context.find_stabilizer_group(qubits)
    registers = [context.new_register() for i in range(len(group))]

    for register, stabilizer in zip(registers, group):
        instructions.append(Tick())
        instructions.append(cliffords.MeasurePauli(targets=([register] + qubits), parameters=stabilizer))

    decoder = context.build_decoder(qubits, registers, abort)

    return Gadget(name, circuit=Circuit(instructions), decoder=decoder)
