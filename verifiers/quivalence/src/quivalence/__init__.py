"""Standalone dense-matrix checker for portable circuit-rule dictionaries."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Mapping

import numpy as np


def _version() -> str:
    try:
        return version("quivalence")
    except PackageNotFoundError:
        return "0.1.0"


def _embedded(gate: Mapping[str, Any], width: int) -> np.ndarray:
    name = str(gate["name"])
    wires = tuple(int(wire) for wire in gate["wires"])
    if len(set(wires)) != len(wires) or any(wire < 0 or wire >= width for wire in wires):
        raise ValueError(f"{name}: invalid circuit wire")
    local = np.asarray(
        [[complex(float(real), float(imag)) for real, imag in row] for row in gate["matrix"]],
        dtype=complex,
    )
    local_dim = 1 << len(wires)
    if local.shape != (local_dim, local_dim):
        raise ValueError(f"{name}: expected a {local_dim}×{local_dim} matrix")
    if not np.isfinite(local).all():
        raise ValueError(f"{name}: matrix contains non-finite entries")
    dim = 1 << width
    result = np.zeros((dim, dim), dtype=complex)
    for column in range(dim):
        bits = [(column >> (width - 1 - index)) & 1 for index in range(width)]
        local_column = 0
        for wire in wires:
            local_column = (local_column << 1) | bits[wire]
        for local_row in range(local_dim):
            row_bits = bits.copy()
            for position, wire in enumerate(wires):
                row_bits[wire] = (local_row >> (len(wires) - 1 - position)) & 1
            row = 0
            for bit in row_bits:
                row = (row << 1) | bit
            result[row, column] += local[local_row, local_column]
    return result


def circuit_matrix(circuit: Mapping[str, Any], *, max_qubits: int = 6) -> np.ndarray:
    """Compose a circuit from its serialized gate matrices and wire indices."""
    width = int(circuit["width"])
    if width < 0 or width > max_qubits:
        raise ValueError(f"circuit width {width} exceeds matrix limit {max_qubits}")
    result = np.eye(1 << width, dtype=complex)
    for gate in circuit["gates"]:
        result = _embedded(gate, width) @ result
    return result


@dataclass(frozen=True)
class MatrixVerifier:
    max_qubits: int = 6
    atol: float = 1e-10

    def check(self, rule: Mapping[str, Any]) -> dict[str, Any]:
        """Return a JSON-serializable rule verdict; no qstack imports are used."""
        rule_id = str(rule.get("id", "<unknown>"))
        configuration = {"max_qubits": self.max_qubits, "atol": self.atol}
        common = {
            "rule": rule_id,
            "backend": "matrix",
            "backend_version": _version(),
            "configuration": configuration,
        }
        try:
            source_circuit = rule["source"]
            target_circuit = rule["target"]
            if int(source_circuit["width"]) != int(target_circuit["width"]):
                raise ValueError("unequal circuit widths")
            source = circuit_matrix(source_circuit, max_qubits=self.max_qubits)
            target = circuit_matrix(target_circuit, max_qubits=self.max_qubits)
        except (KeyError, TypeError, ValueError) as exc:
            return {**common, "status": "UNSUPPORTED", "detail": str(exc)}
        difference = np.abs(source - target)
        worst = tuple(int(index) for index in np.unravel_index(np.argmax(difference), difference.shape))
        error = float(difference[worst])
        if error > self.atol:
            return {
                **common,
                "status": "REFUTED",
                "detail": (
                    f"matrix entry {worst} differs by {error:.6g}: "
                    f"source={source[worst]!r}, target={target[worst]!r}"
                ),
            }
        return {**common, "status": "VERIFIED", "detail": f"maximum matrix error {error:.6g}"}


def verify_rule(rule: Mapping[str, Any]) -> dict[str, Any]:
    """Entry-point function used by qstack and standalone callers."""
    return MatrixVerifier().check(rule)


__all__ = ["MatrixVerifier", "circuit_matrix", "verify_rule"]
