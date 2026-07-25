# qstack MLIR

The default qstack implementation on top of
[xdsl](https://github.com/xdslproject/xdsl), with OpenQASM 3.0 as the surface
language. The original implementation is archived under `qstack.v0/`.

> **Compatibility:** This implementation is now being promoted as the `qstack`
> package. It replaces the legacy Python API archived under `qstack.v0/`; the
> two APIs are not backward compatible.

- **Positioning:** [POSITIONING.md](POSITIONING.md).
- **Spec:** [DESIGN.md](DESIGN.md) (IR), [../docs/superpowers/specs/2026-05-22-openqasm-surface-design.md](../docs/superpowers/specs/2026-05-22-openqasm-surface-design.md) (surface).
- **Running implementation log:** [implementation-notes.md](notes/implementation-notes.md).

## Install (dev)

```bash
source ~/Repos/.venv/qstack/bin/activate
pip install -e ./mlir[qasm,dev]
```

## Run tests

```bash
pytest mlir/tests
```
