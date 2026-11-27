from pauliverse_verifier import verify_rule


def gate(name, wire):
    h = 2**-0.5
    matrix = {"x": [[0, 1], [1, 0]], "h": [[h, h], [h, -h]], "z": [[1, 0], [0, -1]]}[name]
    return dict(name=f"cliffords.{name}", wires=[wire], parameters=[],
                matrix=[[(value, 0) for value in row] for row in matrix])


def test_identity_encoding_checks_relative_phase_and_gate_cancellation():
    def check(names):
        rule = dict(id="one-wire", source=dict(width=1, gates=[gate(name, 0) for name in names]),
                    target=dict(width=1, gates=[]))
        return verify_rule(rule)["status"]

    assert check(["h", "h"]) == "VERIFIED"
    assert check(["z"]) == "REFUTED"


def test_invalid_stabilizers_and_unrecognized_gate_semantics_decline():
    rule = dict(id="logical-x", source=dict(width=1, gates=[gate("x", 0)]),
                target=dict(width=3, gates=[gate("x", i) for i in range(3)]),
                encoding=dict(physical_qubits=3, stabilizers=["+ZZI", "+ZZI"], logical_x="+XXX", logical_z="+ZII"))
    assert verify_rule(rule)["status"] == "UNSUPPORTED"
    rule["encoding"]["stabilizers"][1] = "+IZZ"
    rule["target"]["gates"][0]["matrix"] = gate("z", 0)["matrix"]
    assert verify_rule(rule)["status"] == "UNSUPPORTED"
