import json

import pytest

from qstack.compilation import CompilationResult
from qstack.encoding import Encoding
from qstack.passes import Rep3BitLowering, Rep3PhaseLowering, lower_rep3_bit
from qstack.runtime import CallbackRegistry
from qstack.surface import compile_qasm
from qstack.verification import installed_rule_backends, verify


def logical_one():
    return compile_qasm('''QSTACKQASM 0.1;
include "qstack/cliffords.inc";
qubit[1] q; bit[1] c;
x q[0]; measure q[0] -> c[0];''')


class XXXUnderPhaseCode(Rep3BitLowering):
    """Keep the physical X gates identical, change only the declared code."""
    encoding = Rep3PhaseLowering.encoding


class XUnderHadamardBasis(Rep3BitLowering):
    """Emit the same X on the one physical qubit of an H-basis encoding."""

    encoding = Encoding(1, (), "+Z", "+X")


@pytest.mark.parametrize(("lowering", "expected"), [
    (Rep3BitLowering, "VERIFIED"),
    (XXXUnderPhaseCode, "REFUTED"),
    (Rep3PhaseLowering, "VERIFIED"),  # its actual X implementation emits ZZZ
    (XUnderHadamardBasis, "REFUTED"),
])
def test_pauliverse_checks_the_emitted_gate_site(tmp_path, lowering, expected):
    backends = {backend.name: backend for backend in installed_rule_backends()}
    if "pauliverse" not in backends:
        pytest.skip("install ./verifiers/pauliverse")
    assert backends["pauliverse"].supported_encodings == ("identity", "stabilizer")
    step = lowering().run(logical_one()).save(tmp_path / "rep3.json")
    report = verify(CompilationResult.load(step.artifact_path))
    assert {rule.kind for rule in step.witness.rules} == {"allocation", "gate", "measurement", "identity"}
    gate_rule, = (rule for rule in step.witness.rules if rule.kind == "gate")
    gate, = (item for item in report.rules if item.rule == gate_rule.id)
    assert (gate.status, gate.backend, gate.sites) == (expected, "pauliverse", ("main:n1",))
    assert report.status == ("REFUTED" if expected == "REFUTED" else "UNSUPPORTED")


@pytest.mark.parametrize("lowering", [Rep3BitLowering, XUnderHadamardBasis])
def test_encoded_gate_skips_a_legacy_backend(tmp_path, lowering):
    class LegacyBackend:
        name = "legacy"

        def check(self, rule):
            pytest.fail("an identity-only backend received a stabilizer rule")

    step = lowering().run(logical_one()).save(tmp_path / "rep3.json")
    report = verify(step, backends=(LegacyBackend(),))
    gate_rule, = (rule for rule in step.witness.rules if rule.kind == "gate")
    gate, = (item for item in report.rules if item.rule == gate_rule.id)
    assert gate.status == "UNSUPPORTED"
    assert gate.backend == "none"
    assert "no configured rule backend supports stabilizer" in gate.detail


def test_same_width_encoding_cannot_claim_a_gate_as_identity(tmp_path):
    step = XUnderHadamardBasis().run(logical_one()).save(tmp_path / "step.json")
    data = json.loads(step.artifact_path.read_text())
    gate = next(rule for rule in data["witness"]["rules"] if rule["kind"] == "gate")
    assert gate["source"] == gate["target"]
    gate["kind"] = "identity"
    step.artifact_path.write_text(json.dumps(data))
    report = verify(CompilationResult.load(step.artifact_path), backends=())
    gate_result, = (item for item in report.rules if item.rule == gate["id"])
    assert gate_result.status == "REFUTED"
    assert "requires a semantic rule or widening" in gate_result.detail


def test_incomplete_bundle_is_rejected_before_gate_check(tmp_path):
    result = lower_rep3_bit(logical_one(), CallbackRegistry()).save(tmp_path / "step.json")
    assert verify(result, backends=()).status == "UNSUPPORTED"
    data = json.loads(result.artifact_path.read_text())
    edge = next(e for e in data["witness"]["edges"] if len(e["target"]) == 3)
    edge["target"].pop()
    result.artifact_path.write_text(json.dumps(data))
    report = verify(CompilationResult.load(result.artifact_path), backends=())
    assert report.status == "REFUTED"
    assert "edge types differ" in report.detail
