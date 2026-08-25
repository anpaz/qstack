# qstack

qstack is a research framework for building quantum compiler stacks on top of
[xdsl](https://github.com/xdslproject/xdsl). It provides a linear quantum IR,
a surface language based on a subset of OpenQASM 3, compiler passes,
verification, and execution backends in one Python codebase.

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

Programs enter qstack through the supported OpenQASM 3 subset or direct IR
construction. Compiler passes progressively lower them through instruction-set
dialects, with verification boundaries between layers. The resulting modules
can be evaluated with the included state-vector and Stim-backed runtimes.

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
- `src/qstack/passes/` contains decomposition and QEC transformations.
- `src/qstack/surface/` parses and lowers the supported OpenQASM 3 subset.
- `src/qstack/runtime/` provides execution, noise, and callback infrastructure.
- `src/qstack/verifier.py` enforces qstack-specific IR invariants.
- `tests/` contains unit and end-to-end compiler tests.

The notebooks in `examples/` demonstrate application construction, compilation,
and evaluation. They are end-to-end usage examples rather than tutorials for
implementing new compiler passes.

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
