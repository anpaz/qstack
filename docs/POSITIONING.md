# qstack: Positioning

## Elevator pitch

**qstack is a framework for building quantum compilers whose correctness can be verified across the full stack**, from
a high-level program down to error-corrected machine instructions. These compilation passes are intricate and difficult
to test: a defect does not produce a crash but silently changes the computed result, and because quantum output is
inherently noisy, such corruption is indistinguishable from hardware noise. qstack attaches a machine-checkable
equivalence proof to every compilation step, so correctness is established pass by pass across the entire pipeline. It
is designed to be usable by compiler engineers without a formal-methods background, and requires no proof assistant.

## Why quantum verification differs from the classical case

End-to-end verification of classical programs, from a high-level language down to assembly, has been demonstrated. It
is reasonable to ask whether the quantum case is simply the same problem restated. It is not. The compilation pipeline
differs in three important ways:

- **The computation model is unitary.** Correctness is defined as equivalence of quantum operators rather than of
  values and control flow, so the checks that establish it differ fundamentally from their classical counterparts.
- **Real programs are hybrid.** A quantum program is naturally thought of as a set of unitaries applied to qubits, a
  quantum circuit, and most verification and optimization techniques are built for exactly that model. Even simple
  programs break it: teleportation measures qubits mid-program and applies corrections conditioned on the classical
  outcomes. Error correction does the same at scale, measuring a syndrome, decoding it, and applying a correction during
  execution. The object under verification is therefore not a pure circuit, and techniques that assume one do not apply
  directly.
- **Several abstractions have no classical analog.** Quantum programs are written against resources no physical machine
  provides: arbitrary rotations, any-to-any qubit connectivity, and error-free qubits. Each must be compiled away.

What does carry over is the underlying idea: trustworthy classical compilers are built by attaching a correctness check
to each compilation step. qstack adopts that idea. What it checks, and how, is specific to the quantum setting.

## The problem, and prior work

A quantum compiler cannot be made correct through testing. The input space is intractably large, measuring a state to
inspect it destroys it, and an incorrect result is indistinguishable from noise. Proving an entire quantum compiler
correct in a single step scales poorly: current fully verified tools are limited to a small number of qubits, whereas
error correction requires many thousands.

Substantial prior work exists, and qstack builds directly on it:

- **Per-pass compiler verification.** VOQC/SQIR verifies optimizer and mapping passes in Coq; CertiQ and Giallar verify
  Qiskit passes automatically using symbolic execution and SMT, with Giallar requiring no formal-methods background.
  These target the pre-error-correction, unitary portion of the stack.
- **Stabilizer circuit verification.** The stabilizer/logical-action method (Kliuchnikov, Beverland, Paetznick)
  characterizes the logical action of an encoded circuit exhaustively, including mid-circuit measurement and Pauli
  corrections conditioned on measured parities.
- **Circuit equivalence checking.** MQT QCEC checks whether two circuits implement the same unitary up to global phase,
  and applies this to complete compilation flows: gate-set translation, mapping, and optimization.

These techniques provide the building blocks. The open question is how to verify a complete pipeline that includes
error correction.

## The contribution: a method-agnostic verification framework

Each technique above verifies a single kind of transformation, and the equivalence checkers verify an entire flow at
once, as one before/after comparison. None carries per-step verification across the error-correction encoding boundary,
and none represents a hybrid program natively. To our knowledge, no existing compiler embeds an appropriate check at
every layer, end to end. This is qstack's contribution.

qstack is an IR and frontend designed so that any verification technique can be applied at any layer. Each lowering step
is expressed as a verifiable equivalence check, and the IR ensures that each pass exposes the structure needed for the
least expensive sufficient check:

| Compilation pass                            | Abstraction removed             | Verified by             |
| ------------------------------------------- | ------------------------------- | ----------------------- |
| Gate decomposition (instruction set A to B) | (lowering to a target gate set) | matrix comparison       |
| Gate synthesis                              | arbitrary rotations             | matrix comparison       |
| QEC encoding                                | error-free qubits               | stabilizer verification |
| Layout and routing                          | any-to-any connectivity         | MQT QCEC                |
| Optimization                                | (none; it improves the circuit) | MQT QCEC                |

Most passes reduce to an inexpensive local check: a gate transformation rewrites each gate independently, so
verification is a matrix comparison of the small before/after fragment. Stabilizer verification handles the encoding
pass, for which it is well suited. Only the two whole-kernel passes require the heavier equivalence checker. Whole-stack
verification is tractable because the IR routes each pass to the lightest sufficient check, not because a single
universal verifier is required.

The closest existing capability is QCEC's compilation-flow verification. The differences are worth stating precisely:

- **Coverage of QEC encoding.** QCEC compares two circuits on the same qubits. Encoding maps one logical qubit to many
  physical qubits, which is an encoded logical action rather than a same-space unitary equivalence, and is the domain
  of stabilizer verification. QCEC does not address it.
- **Per-layer rather than monolithic verification.** QCEC performs a single before/after check over the entire flow;
  qstack verifies each pass, which localizes a defect to the responsible pass and allows each pass to use the least
  expensive sufficient technique.
- **Native representation of hybrid programs.** QCEC handles mid-circuit measurement and feedback only by
  de-hybridizing: an optional, off-by-default transformation that defers all measurements to the end and reduces the
  program to a unitary. This increases the qubit count and cannot express the real-time measure-decode-correct loop of
  error correction, whose decoder is arbitrary classical code. qstack retains measurement and feedback in place and
  isolates the decoder, as described below.

Because the framework is method-agnostic, it can use QCEC as the backend for the layers to which QCEC is suited, and
other techniques elsewhere. Every pass is the same kind of object, a verifiable equivalence check, distinguished only by
the technique applied. Error correction is therefore not a special case added to the compiler but one layer among others
in the same framework. Because a code is supplied as a self-contained package, the same verified framework produces a
compiler for any code without re-proving.

## How qstack achieves this

The approach rests on one design decision: classical computation is kept out of the quantum part of the program.

Most quantum representations combine quantum operations with classical variables, arithmetic, and branching. qstack does
not. The quantum program is represented as a graph of purely quantum operations; wherever classical logic is required,
such as decoding a syndrome or selecting a subsequent operation, it is placed behind an explicit **sealed box** that the
compiler treats as opaque. This discipline is what lets the circuit-based techniques above be applied end to end:
because the classical feedback is confined to sealed boxes, a hybrid program is verified without first reducing it to a
unitary, each lowering step remains a pure quantum equivalence check that those techniques can consume, and the
classical decoder within the box is left unmodified.

It also separates trust cleanly, and the separation is symmetric. The compiler is verified on the quantum side, pass by
pass. The sealed boxes pass through compilation unchanged and are either trusted as written or checked separately as
ordinary classical code. That separate verification is possible by design: from the classical code's perspective the
quantum program is itself opaque, since all communication follows a bits-based contract with no access to the quantum
state or circuit. The classical pieces can therefore be written and verified independently of the quantum parts. Because
each step's quantum action remains small and regular, it is checked mechanically rather than by simulation, which allows
the method to scale beyond the small qubit counts at which whole-program proofs become infeasible.

Two consequences follow:

- **Usable without a proof assistant.** Like the automated tools, and unlike the Coq-based ones, qstack requires no
  formal-methods background: a compiler pass is written, and the framework checks it.
- **Scales with program structure rather than state-space size.** Verification cost is determined by the per-operation
  checks, not by the exponential size of the quantum state.
  =
  qstack is organized in three layers: a surface language (`qstackqasm`, a restricted subset of OpenQASM 3.0), an
  intermediate representation (the qstack MLIR dialect), and a verification layer that hosts the per-pass checks.

## Composition of guarantees

The packages also compose. Error-correction codes can be layered, with one code correcting errors that another does
not, and their correctness guarantees compose accordingly: verifying two simple codes establishes the correctness of the
stronger stacked code without additional proof. Stacking the two simplest repetition codes, for example, reconstructs
the Shor code. This is a further benefit of the framework rather than its central claim.

## Summary

> qstack is an IR and framework that allow existing quantum verification techniques to be applied at any compilation
> layer, so that verification runs at every step across the complete error-corrected stack, from OpenQASM to hardware
> instructions, including the error-correction boundary that whole-circuit checkers cannot cross.
