# MQT QCEC verifier plugin

This independently installable plugin checks serialized circuit rules using
MQT QCEC. It does not import qstack or inspect its IR. From the repository root:

```bash
python -m pip install ./verifiers/qcec
```

Installation registers a `qcec` backend in the `qstack.rule_verifiers` entry-point
group. The plugin translates supported gate names to Qiskit circuits and passes
them to MQT QCEC. Unrecognized gates and unavailable dependencies produce an
`UNSUPPORTED` verdict.

Only exact equivalence or equivalence up to a single global phase verifies a
rule. A generic phase-related verdict is unsupported, since it does not by
itself establish preservation of relative phases on arbitrary inputs. Reports
retain QCEC's raw criterion.
