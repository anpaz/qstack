# qstack MLIR

Parallel implementation of qstack on top of [xdsl](https://github.com/xdslproject/xdsl), with OpenQASM 3.0 as the surface language. Lives alongside the original `src/qstack/` (which is unchanged).

- **Positioning:** [POSITIONING.md](POSITIONING.md).
- **Spec:** [DESIGN.md](DESIGN.md) (IR), [../docs/superpowers/specs/2026-05-22-openqasm-surface-design.md](../docs/superpowers/specs/2026-05-22-openqasm-surface-design.md) (surface).
- **Running implementation log:** [implementation-notes.md](implementation-notes.md).

## Install (dev)

```bash
source ~/Repos/.venv/qstack/bin/activate
pip install -e ./mlir[qasm,dev]
```

## Run tests

```bash
pytest mlir/tests
```
