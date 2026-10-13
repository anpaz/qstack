# Quivalence

This is a separate distribution from qstack. It checks one serialized circuit
rule by composing its source and target gate matrices in boundary-wire order.
It does not import qstack or inspect compiler IR.

From the qstack repository root:

```bash
python -m pip install ./verifiers/quivalence
```

qstack discovers the installed `matrix` backend through the
`qstack.rule_verifiers` entry-point group. To run it directly, pass one rule
JSON object to `python -m quivalence rule.json`; the command writes a
JSON verdict to standard output. The check compares matrices up to one global phase, preserving the induced
quantum instrument; relative phases are not ignored. Widths above six qubits return `UNSUPPORTED`.
