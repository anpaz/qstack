# %%
from typing import Callable
from qstack.gadget import Gadget, QubitId, Instruction, GadgetContext
from qstack.paulis import *

import logging

logger = logging.getLogger("qstack")

_lookup_tables = {}


def get_lookup_table(stabilizers: list[dict[str, Pauli]], distance: int):
    if not stabilizers:
        return {}

    key = tuple([v for s in stabilizers for v in s.values()])
    if key in _lookup_tables:
        return _lookup_tables[key]

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
                syndrome = tuple([eval(s.values(), error) for s in stabilizers])
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

    _lookup_tables[key] = table
    return table


# stabilizers = [
#     [I, I, I, X, X, X, X],
#     [I, X, X, I, I, X, X],
#     [X, I, X, I, X, I, X],
#     [I, I, I, Z, Z, Z, Z],
#     [I, Z, Z, I, I, Z, Z],
#     [Z, I, Z, I, Z, I, Z],
# ]
# stabilizers = {tuple(s) for s in stabilizers}

# table = build_lookup_table(stabilizers, 3)
# table


# %%
def stabilizer_for(basis, qubits) -> dict[QubitId, Pauli]:
    return {q: b for (b, q) in zip(basis, qubits)}


# %%
def update_syndrome_bit(bit: int, syndrome: dict[QubitId, Pauli], accumulated_error: dict[QubitId, Pauli]):
    for q in syndrome:
        s = syndrome[q]
        e = accumulated_error.get(q, I)
        if not commutes(s, e):
            bit += 1 + (s.sign // 2) + (e.sign // 2)
    return bit % 2


def SyndromExtraction(
    qubits: list[QubitId], stabilizers: dict[QubitId, Pauli], distance: int = 3, abort: bool = False
):
    ancillas = [QubitId(f"ancilla.{idx}") for idx in range(len(stabilizers))]

    prepare = [Instruction(name="|0⟩", targets=[a]) for a in ancillas]

    compute = (
        [Instruction(name="h", targets=[a]) for a in ancillas]
        + [
            Instruction(name="cx", targets=[a, q])
            for (a, stabilizer) in zip(ancillas, stabilizers)
            for q in stabilizer
            if stabilizer[q] == X
        ]
        + [
            Instruction(name="cz", targets=[a, q])
            for (a, stabilizer) in zip(ancillas, stabilizers)
            for q in stabilizer
            if stabilizer[q] == Z
        ]
        + [Instruction(name="h", targets=[a]) for a in ancillas]
    )

    measure = [Instruction(name="mz", targets=[a]) for a in ancillas]

    def syndrome_decoder(syndrome: tuple[int], context: dict):
        corrections = context.get("corrections", {})
        last_error = {q: corrections.get(q, I) for q in qubits}

        new_syndrome = tuple(
            [update_syndrome_bit(bit, stabilizer, last_error) for (bit, stabilizer) in zip(syndrome, stabilizers)]
        )

        lookup_table = get_lookup_table(stabilizers=stabilizers, distance=distance)
        if new_syndrome in lookup_table:
            new_correction = {q: b for (q, b) in zip(qubits, lookup_table[new_syndrome])}
        else:
            logger.warning(f"Syndrome {new_syndrome} not found in correction table.")
            new_correction = {}

        result_bits = tuple()
        context["corrections"] = last_error | {q: new_correction[q] * last_error[q] for q in new_correction}
        return result_bits, context

    return Gadget(
        name="SyndromeExtraction", prepare=prepare, compute=compute, measure=measure, decode=syndrome_decoder
    )
