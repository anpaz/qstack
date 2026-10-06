"""Contract tests that run without installing qstack."""

from __future__ import annotations

import json
import subprocess
import sys

from quivalence import MatrixVerifier, verify_rule


H = [[(2**-0.5, 0.0), (2**-0.5, 0.0)], [(2**-0.5, 0.0), (-2**-0.5, 0.0)]]
X = [[(0.0, 0.0), (1.0, 0.0)], [(1.0, 0.0), (0.0, 0.0)]]
NEGATIVE_X = [[(0.0, 0.0), (-1.0, 0.0)], [(-1.0, 0.0), (0.0, 0.0)]]


def _gate(name, matrix):
    return {"name": name, "wires": [0], "parameters": [], "matrix": matrix, "attributes": []}


def _rule(source, target, *, width=1):
    return {
        "id": "rewrite",
        "source": {"width": width, "gates": source},
        "target": {"width": width, "gates": target},
    }


def test_cancellation_and_global_phase() -> None:
    cancellation = verify_rule(_rule([_gate("h", H), _gate("h", H)], []))
    assert cancellation["status"] == "VERIFIED"
    assert cancellation["rule"] == "rewrite"
    assert json.loads(json.dumps(cancellation)) == cancellation

    phase = verify_rule(_rule([_gate("x", X)], [_gate("-x", NEGATIVE_X)]))
    assert phase["status"] == "REFUTED"
    assert "matrix entry" in phase["detail"]


def test_unsupported_inputs() -> None:
    assert MatrixVerifier(max_qubits=0).check(_rule([], []))["status"] == "UNSUPPORTED"
    malformed = _rule([_gate("bad", [[(float("nan"), 0.0)]])], [])
    assert verify_rule(malformed)["status"] == "UNSUPPORTED"


def test_cli_reports_verdict_and_exit_code(tmp_path) -> None:
    rule_path = tmp_path / "rule.json"
    rule_path.write_text(json.dumps(_rule([_gate("x", X)], [_gate("-x", NEGATIVE_X)])))
    process = subprocess.run(
        [sys.executable, "-m", "quivalence", str(rule_path)],
        check=False, capture_output=True, text=True,
    )
    assert process.returncode == 1
    assert json.loads(process.stdout)["status"] == "REFUTED"
