"""MQT QCEC verifier for portable, serialized circuit rules."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Mapping


def _qiskit_circuit(circuit: Mapping[str, Any]):
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(int(circuit["width"]))
    for gate in circuit["gates"]:
        name = str(gate["name"])
        method = {
            "cliffords.h": "h", "cliffords.x": "x", "cliffords.y": "y",
            "cliffords.z": "z", "cliffords.s": "s", "cliffords.cx": "cx",
            "cliffords.cz": "cz", "atoms.rz": "rz", "atoms.sx": "sx",
            "atoms.cz": "cz", "h2.u1": "r", "h2.rz": "rz",
            "h2.rzz": "rzz", "h2.zz": "rzz",
        }.get(name)
        if method is None:
            raise ValueError(f"MQT QCEC adapter has no mapping for {name}")
        params = dict(gate["parameters"])
        if name == "h2.u1":
            args = (float(params["theta"]), float(params["phi"]))
        elif name == "h2.zz":
            args = (math.pi / 2,)
        elif method in {"rz", "rzz"}:
            args = (float(params["theta"]),)
        else:
            args = ()
        getattr(qc, method)(*args, *(int(wire) for wire in gate["wires"]))
    return qc


@dataclass(frozen=True)
class QCECVerifier:
    configuration: dict[str, object] = field(default_factory=dict)

    def check(self, rule: Mapping[str, Any]) -> dict[str, Any]:
        """Check one rule; return a JSON-compatible verdict."""
        rule_id = str(rule.get("id", "<unknown>"))
        common = {"rule": rule_id, "backend": "qcec", "configuration": self.configuration}
        try:
            source_rule, target_rule = rule["source"], rule["target"]
            if int(source_rule["width"]) != int(target_rule["width"]):
                raise ValueError("unequal circuit widths")
            from mqt import qcec

            source = _qiskit_circuit(source_rule)
            target = _qiskit_circuit(target_rule)
        except (ImportError, KeyError, TypeError, ValueError) as exc:
            return {**common, "status": "UNSUPPORTED", "detail": str(exc)}
        try:
            result = qcec.verify(source, target, **self.configuration)
        except Exception as exc:
            return {**common, "status": "UNSUPPORTED", "detail": f"QCEC failed: {exc}"}
        criterion = result.equivalence
        raw = getattr(criterion, "name", str(criterion)).lower().rsplit(".", 1)[-1]
        if raw in {"equivalent", "equivalent_up_to_global_phase", "equivalent_up_to_phase"}:
            status = "VERIFIED"
        elif raw == "not_equivalent":
            status = "REFUTED"
        else:
            status = "UNSUPPORTED"
        try:
            backend_version = version("mqt.qcec")
        except PackageNotFoundError:
            backend_version = None
        return {
            **common, "status": status, "detail": str(result),
            "raw_result": raw, "backend_version": backend_version,
        }


def verify_rule(rule: Mapping[str, Any]) -> dict[str, Any]:
    """Entry point consumed by qstack's generic verifier dispatcher."""
    return QCECVerifier().check(rule)


__all__ = ["QCECVerifier", "verify_rule"]
