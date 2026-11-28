# qstack

qstack is a research framework for building quantum compiler stacks on top of
[xdsl](https://github.com/xdslproject/xdsl). It provides a linear quantum IR,
a surface language based on a subset of OpenQASM 3, compiler passes,
verification, and execution backends in one Python codebase.

qstack focuses on the quantum part of hybrid quantum-classical programs. All classical computation, such as decoders, branch conditions, or arithmetic on measurement results, sits behind opaque callbacks: the IR records which measurement bits flow into each callback and which quantum behavior it may select, but never the callback's body. Callbacks are host-language implementations registered by name, and compiler passes and verifiers never inspect them. As a result, qstack works with any hybrid program regardless of what evaluates its classical side, whether that is Python, a decoder library, an FPGA, or a separate classical runtime, and its passes and verification can concentrate entirely on quantum structure while preserving every callback boundary exactly.

A central goal of qstack is **pass verification across every layer of the
stack**. Each transformation should produce IR whose structure, types, and
linear use of quantum and classical values can be checked before the next
lowering layer consumes it. This makes verification part of the compiler
pipeline rather than a final validation step.

The project is primarily intended for researchers and developers working on:

- quantum error-correction transformations;
- circuit optimization and decomposition passes;
- qubit layout and hardware-lowering passes; and
- compiler analyses for hybrid quantum-classical programs.

Programs enter qstack through the [supported OpenQASM 3 subset](docs/QSTACKQASM-design.md)
or direct IR construction. Compiler passes progressively lower them through instruction-set
dialects, with verification boundaries between layers. The resulting modules
can be evaluated with the included state-vector and Stim-backed runtimes.

To learn more about using qstack, take a look at the [examples folder](examples/).

The frontend returns a structurally verified `ModuleOp`. Compiler passes accept
a module or a previous `CompilationResult` and return a `CompilationResult`
containing the transformed module and any verification witness:

```python
from qstack.surface import compile_qasm
from qstack.passes import lower_cliffords_to_h2
from qstack.verification import verify

source = compile_qasm(qasm_text)
target = lower_cliffords_to_h2(source)
target = target.save("step.qstack.json")
report = verify(target)
```

`qstack.validation.validate_module(module)` checks xDSL well-formedness and
qstack's structure, types, and linearity, raising on invalid IR. The frontend
and compiler passes call it automatically.

`verify(result)` independently checks a compiler pass using its source, target, and
transformation witness. It reports `VERIFIED`, `REFUTED`, or `UNSUPPORTED`.
Passes declare an `Encoding`, which determines the qubit bundle width
and defaults to the one-qubit identity encoding. With the optional
[Pauliverse checker](verifiers/pauliverse/) installed, `verify` reports whether
each supported gate implements its logical action. Encoded preparation and
measurement remain unsupported, so inspect `report.rules` for individual
verdicts. See the [Rep3 notebook](examples/rep3_demo.ipynb) for a working example.

For circuit checks, install a verifier such as
[Quivalence](verifiers/quivalence/) (`pip install ./verifiers/quivalence`) or
[MQT QCEC](verifiers/qcec/). Installed verifiers are discovered automatically.
Use `qstack.verification.installed_rule_backends()` to list them. Each backend's
`supported_encodings` indicates whether it can receive gate rules under
`identity`, nonidentity stabilizer encodings (`stabilizer`), or both.
See the [verification design](docs/verification-design.md) for details.

## Installation

qstack requires Python 3.12 or newer. To install it in a fresh virtual
environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

For an editable development installation with the test and build tools:

```bash
python -m pip install -e '.[dev]'
```

Jupyter support can be installed separately:

```bash
python -m pip install -e '.[jupyter]'
```

## Project structure

- `src/qstack/dialect/` defines the core IR and instruction-set dialects.
- `src/qstack/passes/` contains decomposition and QEC transformations, with shared contracts in `contracts.py` and construction checks in `checks.py`.
- `src/qstack/surface/` parses and lowers the supported OpenQASM 3 subset.
- `src/qstack/runtime/` provides execution, noise, and callback infrastructure.
- `src/qstack/validation.py` enforces qstack-specific IR invariants.
- `verifiers/` contains independently installable circuit-rule verifiers.
- `tests/` contains unit and end-to-end compiler tests.

The notebooks in `examples/` demonstrate application construction, compilation,
and evaluation. They are end-to-end usage examples rather than tutorials for
implementing new compiler passes.

## Visualizing dataflow

`qstack.visualize` emits Mermaid flowcharts directly from a kernel's SSA
dataflow. Operations are nodes, SSA values are labeled with their IR names,
qubits are solid wires, measurement bits are bold wires, and the derived host
state is a dotted wire.

Direct calls are inlined by default, so their wires flow through the callee's
operations within an `@kernel` region. Recursive calls remain references to
keep diagrams finite. Pass `inline_calls=False` to show called definitions
within their call-site subgraphs instead.

```python
from qstack.visualize import dataflow

diagram = dataflow(module, kernel="main")
print(diagram.to_mermaid())
diagram.display()
```

`display()` emits Mermaid-fenced Markdown for Jupyter frontends that support
Mermaid rendering. `to_mermaid()` is always available for copying into another
Mermaid-compatible renderer. After `%load_ext qstack.jupyter`, `dataflow` is
already available in the notebook namespace.

## Docket

Docket visualizes a compilation step in your browser. Select a kernel to see
its claim graph, then select a claim to inspect the rule's source and target
patterns and every site that uses that rule. Export requires Graphviz
(`dot` on PATH). The generated HTML opens offline.

### Generate a docket from Python

Starting with a toy-dialect program named `toy_program`, run the compiler pass
and optionally call `verify()` to include its results.

```python
from qstack.passes.toy2cliffords import lower_toy_to_cliffords
from qstack.verification import verify
from qstack.verification.viewer import generate_docket

target = lower_toy_to_cliffords(toy_program)
report = verify(target)

generate_docket(target, report=report)
```

Open `docket.html` in the current directory. It shows the step verdict, which
rule backends were available, and whether each kernel's claim graph matched
both IR snapshots. Each claim node carries the verdict of its rule.
Select a rule to see its verifier and any fallback attempts. Call
`generate_docket(target)` to view the witness on its own.

### Save the compilation result and verification report as JSON

```python
target = target.save("step.json")
report.save("verification.json")
```

`step.json` contains the witness and the source and target IR.
`verification.json` contains the results of `verify()`, including the available
backends and the attempts for each rule.

### Generate a docket from existing files

Pass the saved paths to regenerate `docket.html` from the recorded results.

```python
from qstack.verification.viewer import generate_docket

generate_docket("step.json", report="verification.json")
```

The same export is available from the command line.

```bash
python -m qstack.verification.viewer step.json --report verification.json
```

Omit the report argument to view the saved witness on its own.

## Development

Run the test suite from the repository root:

```bash
pytest
```

Build the source distribution and wheel with:

```bash
python -m build
```

For the IR design and project motivation, see
[DESIGN.md](docs/DESIGN.md) and [POSITIONING.md](docs/POSITIONING.md).

## License

qstack is available under the [MIT License](LICENSE).
