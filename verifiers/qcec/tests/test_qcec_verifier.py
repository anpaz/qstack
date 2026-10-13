"""Tests for the standalone QCEC plugin's serialized-rule contract."""

from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from qcec_verifier import QCECVerifier, verify_rule
from qcec_verifier import _qiskit_circuit


def _rule():
    h = {"name": "cliffords.h", "wires": [0], "parameters": []}
    return {
        "id": "cancel",
        "source": {"width": 1, "gates": [h, h]},
        "target": {"width": 1, "gates": []},
    }


@pytest.mark.parametrize("criterion, status", [
    ("equivalent", "VERIFIED"),
    ("equivalent_up_to_global_phase", "VERIFIED"),
    ("equivalent_up_to_phase", "UNSUPPORTED"),
    ("not_equivalent", "REFUTED"),
])
def test_qcec_checks_only_serialized_rule(monkeypatch, criterion, status) -> None:
    calls = []

    class QuantumCircuit:
        def __init__(self, width):
            self.width = width
            self.gates = []

        def h(self, wire):
            self.gates.append(("h", wire))

    def compare(source, target, **configuration):
        calls.append((source, target, configuration))
        return SimpleNamespace(equivalence=SimpleNamespace(name=criterion))

    qiskit = ModuleType("qiskit")
    qiskit.QuantumCircuit = QuantumCircuit
    mqt = ModuleType("mqt")
    mqt.qcec = SimpleNamespace(verify=compare)
    monkeypatch.setitem(sys.modules, "qiskit", qiskit)
    monkeypatch.setitem(sys.modules, "mqt", mqt)

    verdict = QCECVerifier({"timeout": 3}).check(_rule())
    assert verdict["status"] == status
    assert verdict["raw_result"] == criterion
    assert calls[0][0].gates == [("h", 0), ("h", 0)]
    assert calls[0][1].gates == []
    assert calls[0][2] == {"timeout": 3}
    json.dumps(verdict)


def test_unsupported_rule_does_not_need_qcec() -> None:
    rule = _rule()
    rule["target"] = {"width": 2, "gates": []}
    assert verify_rule(rule)["status"] == "UNSUPPORTED"


def test_qiskit_gate_mapping_when_installed() -> None:
    pytest.importorskip("qiskit")
    circuit = _qiskit_circuit({
        "width": 2,
        "gates": [
            {"name": "cliffords.h", "wires": [0], "parameters": []},
            {"name": "h2.zz", "wires": [0, 1], "parameters": []},
        ],
    })
    assert [instruction.operation.name for instruction in circuit.data] == ["h", "rzz"]


def test_qcec_real_integration_when_installed() -> None:
    pytest.importorskip("qiskit")
    pytest.importorskip("mqt.qcec")
    assert verify_rule(_rule())["status"] == "VERIFIED"
