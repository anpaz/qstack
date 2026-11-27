# Pauliverse gate checker

From the qstack repository root, install the checker in the Python environment running qstack:

```sh
python -m pip install ./verifiers/pauliverse
```

Call `verify(lower_rep3_bit(program, registry))` and inspect `report.rules` as in the [Rep3 notebook](../../examples/rep3_demo.ipynb). Each matching site refers to a rule with its own verdict and backend. The whole encoded step remains unsupported when its preparation or measurement needs checking.

The checker tests a single logical qubit with a declared code. It constructs the encoded Bell state from the code stabilizers and the logical X and Z paired with X and Z on a reference qubit. Pauliverse propagates the physical gates on the data and the complex conjugates of the logical gates on the reference. Preserving every signed generator establishes the two actions agree on the entire code space up to one global phase. Stabilizer rank and commutation are checked before preparation.

The adapter accepts real Clifford X, Z and H gates and wire permutations emitted as swaps. It checks gate matrices and ordered ports. Other gates and multi-logical-qubit rules return `UNSUPPORTED`. Pauliverse registers once through `qstack.rule_verifiers` and declares support for identity and stabilizer encodings on its entry-point callable.

List installed backends and their encoding capabilities from the same Python environment as qstack.

```python
from qstack.verification import installed_rule_backends

for backend in installed_rule_backends():
    print(backend.name, backend.supported_encodings)
```
