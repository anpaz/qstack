"""Check G E = E g on one logical qubit, up to global phase."""
from importlib.metadata import version

from paulimer import (
    CliffordUnitary, OutcomeCompleteSimulation, PauliGroup, SparsePauli, UnitaryOpcode,
)

# These gates are real, so their action on the reference half of a Bell
# pair equals their complex conjugate. Unsupported gates must decline.
_H = 2**-0.5
_GATES = {
    "cliffords.x": (UnitaryOpcode.X, ((0, 1), (1, 0))),
    "cliffords.z": (UnitaryOpcode.Z, ((1, 0), (0, -1))),
    "cliffords.h": (UnitaryOpcode.Hadamard, ((_H, _H), (_H, -_H))),
    "qstack.swap": (UnitaryOpcode.Swap, ((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1))),
}


def _generators(code, n):
    """Stabilizers of the encoded Bell state, with the reference on wire n."""
    if type(code["physical_qubits"]) is not int or code["physical_qubits"] != n or len(code["stabilizers"]) != n - 1:
        raise ValueError("invalid stabilizer count or code width")
    generators = []
    pairs = [(word, "") for word in code["stabilizers"]]
    pairs.extend(((code["logical_x"], f"X_{n}"), (code["logical_z"], f"Z_{n}")))
    for word, reference in pairs:
        if len(word) != n + 1 or word[0] not in "+-" or set(word[1:]) - set("IXYZ"):
            raise ValueError(f"invalid signed Pauli word {word!r}")
        terms = [f"{p}_{i}" for i, p in enumerate(word[1:]) if p != "I"]
        if reference:
            terms.append(reference)
        if not terms:
            raise ValueError("identity is not an independent code generator")
        sign = "-" if word.startswith("-") else ""
        generators.append(SparsePauli(sign + " ".join(terms)))
    group = PauliGroup(generators)
    if not group.is_stabilizer_group or group.binary_rank != n + 1:
        raise ValueError("code and logical Paulis do not define a unique encoded Bell state")
    return generators


def _apply(simulation, circuit, layout):
    for gate in circuit["gates"]:
        name = gate["name"]
        if name not in _GATES:
            raise ValueError(f"unsupported gate {name}")
        opcode, expected = _GATES[name]
        matrix = tuple(tuple(complex(*entry) for entry in row) for row in gate["matrix"])
        wires = gate["wires"]
        if matrix != expected or gate["parameters"]:
            raise ValueError(f"unsupported semantics for {name}")
        arity = len(expected).bit_length() - 1
        if (len(wires) != arity or len(set(wires)) != arity
                or any(type(i) is not int or not 0 <= i < len(layout) for i in wires)):
            raise ValueError(f"invalid wires for {name}")
        simulation.apply_unitary(opcode, [layout[i] for i in wires])


def verify_rule(rule):
    """Entry point for JSON circuit rules. All comparisons retain Pauli signs."""
    verdict = dict(rule=rule["id"], backend="pauliverse", backend_version=version("paulimer"))
    try:
        source, target = rule["source"], rule["target"]
        n = target["width"]
        if type(source["width"]) is not int or source["width"] != 1 or type(n) is not int or n < 1:
            raise ValueError("only one logical input qubit is supported")
        code = rule.get("encoding", dict(physical_qubits=1, stabilizers=(), logical_x="+X", logical_z="+Z"))
        generators = _generators(code, n)
        wires = list(range(n + 1))
        sim = OutcomeCompleteSimulation(n + 1)
        sim.apply_clifford(CliffordUnitary.group_encoding_clifford_of(generators, n + 1), wires)
        # (G ⊗ conjugate(g)) preserves |E⟩ exactly when GE = Eg up to phase.
        _apply(sim, source, [n])
        _apply(sim, target, wires[:-1])
        for generator in generators:
            if not sim.is_stabilizer(generator):
                return dict(verdict, status="REFUTED", detail=f"encoded Bell stabilizer {generator} is not preserved")
        return dict(verdict, status="VERIFIED", detail="all signed encoded Bell stabilizers preserved")
    except (KeyError, TypeError, IndexError, ValueError) as error:
        return dict(verdict, status="UNSUPPORTED", detail=str(error))


verify_rule.supported_encodings = ("identity", "stabilizer")
