# qstack: Positioning and Research Thesis

## What is qstack?

qstack is a compiler framework for the fault-tolerant quantum software stack.
It represents quantum computation as compact linear SSA DAGs connected through
opaque classical boundaries, enabling compositional QEC lowering and modular
compiler verification.

## Naming

The original qstack version used an implicit measurement stack. The new
qstack IR replaces that runtime mechanism with explicit SSA values, but the
name still fits the broader project.

qstack targets the fault-tolerant quantum software _stack_: logical programs,
QEC layers, decoders, hardware lowering, and runtime execution. The name also
reflects the central composition model: independently authored QEC and lowering
passes can be stacked while preserving their interfaces.

## Elevator pitch

**qstack makes fault-tolerant quantum compilation modular.** It keeps classical
computation out of the quantum IR, representing quantum programs as compact
linear SSA DAGs connected through opaque classical boundaries. As a result, QEC
layers compose like ordinary compiler passes, programs remain structured as
they scale, and compiler correctness becomes amenable to modular verification.

## What problem is qstack solving?

Fault-tolerant quantum compilation is not compositionally modular.

A QEC pass does more than rewrite gates: it introduces physical qubits,
measurements, decoding, and measurement-driven corrections. After one such
pass, later transformations must operate on a hybrid quantum-classical
program. Composing QEC layers therefore requires each pass to preserve
classical feedback introduced by the others.

qstack separates these concerns. A QEC pass rewrites quantum structure and
inserts explicit decoder boundaries that restore the logical interface
expected downstream. Subsequent passes can compose without inspecting or
rewriting decoder implementations.

## Key insight

**Classical computation does not need to live inside the quantum compiler.**

Most hybrid quantum representations combine quantum operations with classical
expressions, variables, and control flow. qstack keeps classical computation
behind explicit opaque boundaries:

- `qstack.decode` transforms physical measurement outcomes into logical
  outcomes.
- `qstack.select` chooses among a statically known set of quantum
  continuations.

The quantum IR contains no classical expressions, mutable classical state, or
embedded classical control-flow graph. Each quantum region is a control-free
linear SSA DAG. The complete program is a graph of these DAGs connected through
explicit classical boundaries.

Qubits and measurement outcomes are linear SSA values. Decoders consume
physical outcomes and produce logical outcomes. This gives compiler passes a
small, regular semantic object to transform and analyze.

## Compositional QEC lowering

Each QEC pass has an interface-preservation contract:

```text
logical quantum DAG
        |
        v
physical quantum DAG + explicit decoder
        |
        v
same logical interface
```

A pass expands logical operations, introduces physical measurements, and
decodes them back into the logical outcomes expected by downstream consumers.
The next pass can operate on that result without understanding the internal
implementation of the previous QEC layer.

## Opportunities

### Compact representation

Fault-tolerant programs remain structured for as long as possible.

- Repeated quantum behavior remains a named function or recursive
  continuation.
- Classical decisions select existing symbols rather than synthesize or
  duplicate circuits at runtime.
- QEC transformations can operate at logical abstraction levels before
  lowering to physical instructions.
- Higher-level dialects can represent encoded resources, such as surface-code
  patches, without immediately expanding them into physical qubits.

The eventual executable schedule may still be large. The goal is to delay
materialization until a backend requires that detail.

### Graph-local optimization

Keeping classical computation outside the quantum IR preserves quantum regions
as dependency DAGs. This allows quantum rewrites to operate on a regular graph
representation without also traversing an embedded classical control-flow
graph.

### Modular verification

The qstack IR separates the proof obligations:

- Linearity catches dropped, duplicated, and misrouted resources.
- Quantum regions expose explicit SSA dependency graphs.
- Graph-based techniques can analyze quantum-region equivalence.
- Decoder correctness can be analyzed separately as classical code.
- Compiler passes can be checked against local interface-preservation
  contracts.

This does not by itself make the compiler formally verified. It provides a
representation suited to modular verification.

## Scope

qstack does not aim to represent arbitrary runtime circuit synthesis or
unrestricted mutable classical state inside the quantum IR.

It preserves the measurement-driven control patterns targeted by
fault-tolerant workflows, including syndrome decoding, conditional correction,
teleportation fixups, postselection, repeat-until-success protocols, and many
lattice-surgery decisions.
