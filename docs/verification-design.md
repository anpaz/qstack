# Verifying qstack compiler passes

## 1. Goal and scope

This document defines the semantic obligations that qstack compiler passes must satisfy. It is intentionally independent of the mechanism that will discharge them. The executable language is the kernel-only IR specified in [`DESIGN.md`](DESIGN.md).

The goal is **semantic preservation**. For every fixed callback registry and initial callback state, the compiled `@main` kernel must denote an instrument related to the source `@main` kernel by the representation relation declared by the pass. The goal is not equality of IR, equality of SSA result lists, or unchanged physical output wires: a pass may change representations, introduce internal measurements, widen physical resources, and rewrite every unitary. The relation defines which externally meaningful behavior is preserved.

### 1.1 Principles

- **P1. One semantic obligation.** Kernel, instruction, and dialect-lowering transformations are all instances of semantic preservation expressed as instrument preservation modulo a representation relation.
- **P2. Verification does not trust the pass.** Obligations are checked from input and output IR artifacts. A pass cannot certify itself by an assertion about what it intended to rewrite.
- **P3. Existing callbacks are interfaces.** A pass preserves every callback invocation already present in its input module; it never reasons from or rewrites that callback's host implementation. Callbacks are deterministic but may be stateful, so this includes their invocation order and multiplicity. This is an interface-preservation lemma needed for semantic preservation, not the end goal by itself.
- **P4. New callback behavior is an obligation.** When a pass introduces a decoder or a local selector, quantum verification derives the finite classical behavior required for preservation and reports it for a classical verifier to discharge.
- **P5. Composition is the scaling strategy.** Verified local replacements and verified kernel summaries compose into a claim about `@main`.
- **P6. Failures are attributable.** A refutation identifies the kernel or operation, observable, branch, callback contract, or local relation that failed.

### 1.2 Noiseless boundary

This document verifies noiseless semantics only. It does not claim fault tolerance, noise resilience, a threshold, or correct behavior under a noisy syndrome-extraction circuit.

An error tag on an introduced select case has a limited current meaning: the case claims to correct a named error in a stated local reference frame. The quantum verifier may check that local correction identity. A later noisy design may add error distributions, reachability under faults, and fault-tolerance claims; none are part of the present correctness statement.

## 2. Semantic model

### 2.1 Programs are named kernels

A module contains named kernels and callback declarations. `qstack.kernel @main` is the program. `qstack.call` and `qstack.select` invoke other named kernels; there is no executable function layer.

A kernel with borrowed inputs `in`, surviving qubit outputs `out`, and bit results denotes a quantum instrument:

```
⟦K⟧ : D(H_in) → D(H_out ⊗ H_bits)
```

The fresh qubits declared by `allocates N` are internal workspace, initialized to `|0⟩` and measured before the kernel returns. Internal measurement outcomes consumed by `decode` or `select` are summed out by the denotation. Returned bits remain part of the instrument output.

A direct call composes the callee's instrument with the caller. A selected case is a call to one member of a finite, statically named kernel menu.

### 2.2 Fixed callbacks

At runtime, a module is evaluated against one fixed callback registry and initial callback state. Each callback is a deterministic stateful computation: its result and next state are fixed by its current state and received values. A selector receives named bit inputs and returns one of the labels in a select's finite case map; a decoder receives a finite bit tuple and returns one bit. Their implementations are opaque to the quantum compiler. The finite case map is a validation boundary: every quantum behavior the selector may choose is a named, statically available kernel that the verifier can inspect.

The word _fixed_ means more than preserving a declaration. For a callback use already in a pass input, the compiled module must make the same runtime call:

- the same callback symbol and declaration signature;
- the same named selector inputs and the same finite label-to-kernel case map;
- corresponding runtime bit values;
- the same order and multiplicity of invocations; and
- the same reachability behavior, including correlations with live quantum outputs.

The compiler is not allowed to replace, wrap, drop, duplicate, retarget, reorder, or otherwise change such a callback invocation. It need not know what answer the callback gives: the same fixed implementation and initial callback state are used before and after compilation. Exact trace preservation means preserving each invocation's kind, symbol, position, and runtime inputs. It is necessary because a stateful callback can make a later result depend on earlier invocations. Determinism then ensures the two executions have the same callback results and state evolution. This trace condition preserves the opaque host interface; the kernel square below is what establishes the program's semantic preservation.

A pass may not add a new use of a callback declaration already present in its input module: that would change the callback's multiplicity and trace. A newly introduced callback use must have a fresh callback declaration and the corresponding classical obligation described in Section 4.

The requirement is stated per pass input, not by callback origin. If one pass adds a callback declaration and use, the next pass treats it as an ordinary pre-existing fixed callback.

### 2.3 Interface boundary

The interface boundary is the set of values delivered to a callback and the values returned by `@main` to the host. A kernel-to-kernel call boundary is not a host interface; its bits and qubits are internal qstack dataflow. In particular, a pass may move physical measurement plumbing inside a kernel as long as a pre-existing callback receives the corresponding logical value.

## 3. Representation relation and kernel obligation

A kernel-level pass supplies a representation relation. For a QEC pass it is an encoding isometry `V`; a lowering or same-representation optimization uses the identity. The relation is generated by the qstack types:

```
R_qubit(ρ_L, ρ_P)  iff  ρ_P = V ρ_L V†
R_bit(b_L, b_P)    iff  b_L = d(b_P), or b_L = b_P when d is identity
R_(τ1 × τ2)        pointwise
```

Here `d` is the decoder on the explicit dataflow path between a physical bit and its logical consumer. For an introduced decoder, its required behavior is not silently trusted: it becomes a classical obligation derived from the quantum relation.

Two source and compiled kernels are related when their instruments satisfy the commuting square:

```
(id_Q ⊗ d) ∘ ⟦K_P⟧ ∘ V^⊗|in|
    =
(V^⊗|out| ⊗ id_bits) ∘ ⟦K_L⟧
```

This is an equality after interpreting the two kernels through the representation relation, not a requirement that their raw result lists be equal. It includes returned-bit distributions and their correlations with surviving quantum outputs. It covers consumed borrows because a consumed input is present in `in` and absent from `out`; it covers allocations because fresh qubits are internal to the kernel denotation.

## 4. Callback rules

### 4.1 Existing decoders and selectors

For every `qstack.decode` and `qstack.select` use present in a pass input, the output must preserve the callback interface described in Section 2.2. In particular:

- a pre-existing selector retains its callback symbol, bit names, case labels, and case kernel symbols;
- a pre-existing decoder retains its callback symbol and input arity;
- corresponding bit operands carry the same runtime values under `R_bit`; and
- each case kernel remains related to the kernel named by the same label.

Case kernel bodies and kernel signatures may be transformed by the pass, but the callback-visible case map does not change. The callback is not reverified and no new contract is generated for it.

### 4.2 Newly introduced decoders

A pass may introduce `qstack.decode` only as part of a local replacement whose quantum instrument preserves the fragment it replaces. For example, an encoded measurement may produce physical bits, decode them, and expose the original logical bit to the rest of the kernel. The decoder declaration and every such new use are fresh relative to the pass input.

The quantum verifier does not execute or inspect the decoder implementation. It derives and reports a finite classical obligation containing:

1. the callback symbol and input layout;
2. the reachable input bit tuples in the noiseless relation;
3. the output required for each reachable tuple; and
4. any explicitly unconstrained tuples.

A classical verifier is responsible for checking that the registered decoder satisfies that obligation for the required call histories. Until then, the quantum result is verified modulo the reported decoder obligation.

### 4.3 Newly introduced selectors

A pass may introduce a `qstack.select` only to replace a unitary or identity fragment. It may not introduce a select as a replacement for an arbitrary kernel. Its selector declaration and use are fresh relative to the pass input. This keeps the quantum proof local and lets kernel correctness follow by composition.

Every nontrivial case of such a select carries an error tag identifying the error it claims to correct. The no-error case implements the replaced unitary or identity directly. The quantum verifier checks each tagged case in its declared reference frame. For an error `E` occurring after a replaced operation `U`, a correction continuation `C_E` must satisfy:

```
C_E E U = U
```

Equivalently, `C_E E = I` on the relevant representation space. A tag for an error at another point in the circuit must state that point, so the verifier uses the corresponding conjugated relation.

From the measurement/correction structure and these tags, the quantum verifier reports the finite syndrome-to-case behavior required of the new selector. It does not inspect or run the selector's host implementation. A classical verifier later checks that deterministic stateful implementation against the reported obligation for the required call histories.

The selector and its cases are fixed after introduction. Every later pass must preserve them under the existing-callback rule, just as it preserves callbacks written in the original source module.

### 4.4 Introduced classical values

Bits introduced solely for a new decoder or local selector are internal. They must not reach a pre-existing callback or `@main` result without an explicit relation that restores the source observable. This prevents a transformation from adding a new opaque classical interface.

## 5. Composition

The following semantic facts are required for the end-to-end claim:

- **Local composition.** Related instruction replacements compose sequentially. This is what lets a newly introduced decoder or selector be justified at its replacement site rather than against an enclosing kernel.
- **Kernel calls.** If a callee kernel pair is related, replacing a `qstack.call` with the corresponding compiled call preserves the caller's relation.
- **Kernel composition.** If all local fragments in a kernel are related and every pre-existing callback interface is preserved, the source and compiled kernels are related.
- **Root adequacy.** If every reachable named kernel pair is related, all pre-existing callback uses are preserved, and every added callback obligation is discharged, the source and compiled `@main` kernels are related for the fixed callback registry and initial callback state.

These statements rely on linearity: it ensures there are no unaccounted wires, implicit copies, aliases, or silent discards between local obligations.

## 6. Verdicts and obligation handoff

Quantum verification produces one of:

- **VERIFIED**, when all quantum obligations and classical obligations have been discharged;
- **VERIFIED MODULO CLASSICAL OBLIGATIONS**, with the finite decoder and/or selector contracts that remain to be checked;
- **REFUTED**, naming the failing operation, kernel, branch, relation, or callback interface; or
- **UNSUPPORTED**, when the transformation lies outside the supported quantum reasoning fragment.

The obligation handoff to a classical verifier is part of the design boundary, but its data format, the classical verifier, and integration APIs are not fixed here.

## 7. Deliberately deferred

This document does not yet choose:

- concrete verifier algorithms, matrix/stabilizer representations, or external tools;
- the obligation data structure or pass-manager integration;
- an API through which a pass declares a representation relation or error tag;
- the parser and runtime representation of the target IR; or
- noisy and fault-tolerance verification.

Those are implementation-planning work after the semantic model in this document and `DESIGN.md` has been reviewed together.

## 8. Related work and lineage

The intended architecture follows established obligation-driven and translation validation practice: an untrusted transformation produces artifacts that are checked independently, with unsupported cases reported explicitly. Relevant precedents include [Why3](https://www.why3.org/), [Alive2](https://github.com/AliveToolkit/alive2), [CompCert](https://compcert.org/), [VOQC](https://arxiv.org/abs/1912.02250), [CertiQ](https://arxiv.org/abs/1908.08963), [MQT QCEC](https://github.com/munich-quantum-toolkit/qcec), and [Stabilizer Circuit Verification](https://arxiv.org/abs/2309.08676).

qstack's distinctive requirement is to preserve opaque callback interfaces while deriving, rather than trusting, the finite classical contracts needed by newly introduced quantum/classical fragments.
