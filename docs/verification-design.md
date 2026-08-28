# Verifying qstack compiler passes

## 1. Goal and scope

This document defines the semantic obligations that qstack compiler passes must satisfy. It is intentionally independent of the mechanism that will discharge them. The executable language is the kernel-only IR specified in [`DESIGN.md`](DESIGN.md).

The goal is **semantic preservation**. For every fixed callback registry and initial callback state, the compiled `@main` kernel must denote an instrument related to the source `@main` kernel by the representation relation declared by the pass. The goal is not equality of IR, equality of SSA result lists, or unchanged physical output wires: a pass may change representations, introduce internal measurements, widen physical resources, and rewrite every unitary. The relation defines which externally meaningful behavior is preserved.

Section 3 states the contract a pass must honor: what it declares, which rewrites are permitted, and the callback rules. Section 4 describes how verification checks that contract from the IR artifacts alone.

### 1.1 Principles

- **P1. One semantic obligation.** Kernel, instruction, and dialect-lowering transformations are all instances of semantic preservation expressed as instrument preservation modulo a representation relation.
- **P2. Verification does not trust the pass.** Obligations are checked from input and output IR artifacts. A pass cannot certify itself by an assertion about what it intended to rewrite.
- **P3. Existing callbacks are interfaces.** A pass preserves every callback invocation already present in its input module; it never reasons from or rewrites that callback's host implementation. Callbacks are deterministic but may be stateful, so this includes their invocation order and multiplicity. This is an interface-preservation lemma needed for semantic preservation, not the end goal by itself.
- **P4. New callback behavior is an obligation.** When a pass introduces a decoder or a local selector, quantum verification derives the finite classical behavior required for preservation and reports it for a classical verifier to discharge.
- **P5. Operations are checked; kernels are composed.** The goal is never to construct two kernels' instruments and test them for equality: a denotation depends on the registered callback implementations, which the verifier never inspects, and the obligation quantifies over all of them. Each local replacement is checked to change the state exactly as the operation it replaces does, and composition lifts those checks, with kernel summaries, into the claim about `@main`. Transformations with no per-operation decomposition need a different unit of locality before they can be checked; the certified cacho of Section 3.2 is that unit for unitary runs.
- **P6. Failures are attributable.** A refutation identifies the kernel or operation, observable, branch, callback contract, or local relation that failed.

### 1.2 Noiseless boundary

This document verifies noiseless semantics only. It does not claim fault tolerance, noise resilience, a threshold, or correct behavior under a noisy syndrome-extraction circuit.

An error tag on an introduced select case has a deliberately limited meaning: the case claims to correct a named error in a stated local reference frame. The tag is specified here and in `DESIGN.md` but not yet implemented; today `qstack.select` carries no such attribute. The quantum verifier may check that local correction identity. A later noisy design may add error distributions, reachability under faults, and fault-tolerance claims; none are part of the present correctness statement.

## 2. Semantic model

### 2.1 Programs are named kernels

A module contains named kernels and callback declarations. `qstack.kernel @main` is the program. `qstack.call` and `qstack.select` invoke other named kernels; there is no executable function layer.

A kernel with borrowed inputs `in`, qubit results `out`, and bit results `bits` denotes a quantum instrument:

```
⟦K⟧ : states(in) → states(out, bits)
```

`states(X)` is the set of density operators over the systems in `X`; the `bits` register is classical, diagonal in the computational basis. `⟦K⟧` is completely positive and trace preserving, and the classical register is what makes it an instrument: outcome probabilities and per-outcome post-states travel in the same map. Borrowed bits parameterize the family, one map per assignment of their values.

The fresh qubits declared by `allocates N` are initialized to `|0⟩`. Each is either measured within the invocation or returned as a qubit result, so `out` may contain fresh qubits: teleportation consumes its borrowed qubit and returns the state on a fresh carrier. Internal measurement outcomes consumed by `decode` or `select` are summed out by the denotation. Returned bits remain part of the instrument output.

A direct call composes the callee's instrument with the caller. A selected case is a call to one member of a finite, statically named kernel menu.

### 2.2 Fixed callbacks

At runtime, a module is evaluated against one fixed callback registry and initial callback state. Each callback is a deterministic stateful computation: its result and next state are fixed by its current state and received values. A selector receives a positional tuple of bits and returns one of the labels in a select's finite case map; a decoder receives a finite bit tuple and returns one bit. Their implementations are opaque to the quantum compiler. The finite case map is a validation boundary: every quantum behavior the selector may choose is a named, statically available kernel that the verifier can inspect.

The word _fixed_ means more than preserving a declaration. For a callback use already in a pass input, the compiled module must make the same runtime call:

- the same callback symbol and declaration signature;
- the same selector arity and bit operand order, and the same finite label-to-kernel case map;
- corresponding runtime bit values;
- the same order and multiplicity of invocations; and
- the same reachability behavior, including correlations with live quantum outputs.

The compiler is not allowed to replace, wrap, drop, duplicate, retarget, reorder, or otherwise change such a callback invocation. It need not know what answer the callback gives: the same fixed implementation and initial callback state are used before and after compilation. Exact trace preservation means preserving each invocation's kind, symbol, position, and runtime inputs. It is necessary because a stateful callback can make a later result depend on earlier invocations. Determinism then ensures the two executions have the same callback results and state evolution. This trace condition preserves the opaque host interface; the kernel square of Section 4.1 is what establishes the program's semantic preservation.

A pass may not add invocations of a callback declared in its input module: that would change the callback's multiplicity and trace. The constraint is on the runtime trace, not the static operation count. A transformation that duplicates a callback operation without changing when it executes, as inlining a kernel into its caller does, keeps the trace intact, because a call executes either the inlined copy or the callee, never both. The local method of Section 3.2 nevertheless enforces a stricter static proxy, checkable without reachability reasoning: each pre-existing callback use maps to exactly one compiled use within each body copy of the decomposition, and copies arise only through the claimed inlining rewrite of Section 3.2. A newly introduced callback use must have a fresh callback declaration and the corresponding classical obligation described in Section 3.3.

The requirement is stated per pass input, not by callback origin. If one pass adds a callback declaration and use, the next pass treats it as an ordinary pre-existing fixed callback.

### 2.3 Interface boundary

The interface boundary is the set of values delivered to a callback and the values returned by `@main` to the host. A kernel-to-kernel call boundary is not a host interface; its bits and qubits are internal qstack dataflow. In particular, a pass may move physical measurement plumbing inside a kernel as long as a pre-existing callback receives the corresponding logical value.

## 3. The pass contract

This section is the rulebook for pass authors: what a pass declares, what it may rewrite, what it must do about callbacks, and which transformations fall outside the contract. Section 4 describes how each rule is checked.

### 3.1 What a pass declares

A pass may change how qubits and bits are represented, and it must declare how: this declaration is its representation relation. A QEC pass declares an encoding isometry `V` and a decoder `d`. For the three-qubit repetition code, one logical qubit becomes three physical qubits carrying the encoded state, and one logical measurement bit becomes the majority vote of three physical bits. A dialect lowering or same-representation optimization declares the identity for both. Section 4.1 states the relation formally; every obligation in this section is read through it.

The declaration is a claim, not a trusted input. Verification checks the module pair against the declared relation, so a false declaration is refuted and a relation the checker cannot handle yields UNSUPPORTED (Section 5); a claim directs the checks and can affect completeness, never soundness (P2). The error tag on an introduced correction case (Section 3.3) is the per-case instance of the same pattern: it claims which error the case corrects, and the claim is checked, not believed. The cacho certificate (Section 3.2) is a third instance: it claims a rewrite rule and the sites where it was applied, and the verifier checks both the rule and the sites. An inlining claim (Section 3.2) is a fourth: it names the call site and the callee, and the verifier checks the copy against the callee's body.

### 3.2 Permitted rewrites

A pass transforms a kernel operation by operation: each source operation maps to a fragment of the compiled kernel, every compiled operation belongs to exactly one fragment, and the table below is the complete menu of permitted replacements. Each row states what the replacement owes; anything not in the table is outside the contract (Section 3.4).

| source operation | permitted replacement | obligation |
|---|---|---|
| unitary | a unitary sequence from the target dialect, possibly empty when the source acts as the identity through the relation, or a measurement-and-correction fragment built from fresh symbols (rule C3) | the fragment implements the unitary through the representation relation on every branch; each tagged case passes its correction check (Section 4.3); no introduced bit escapes (rule C4) |
| `qstack.measure` | physical measurements feeding one fresh decode, delivering one bit (rule C2) | the delivered bit is related by `R_bit`; the decoder's finite contract is reported for classical discharge (Section 4.3) |
| `qstack.call` | a call to the same kernel symbol, operands and results through the relation, or a claimed inline: a copy of the callee's input body at the call site | for the call: none locally, the callee pair is related (Section 4.4); for an inline: the copy matches the callee's input body (Section 4.2) |
| `qstack.select`, pre-existing | the same select: selector symbol, labels, and case kernel symbols unchanged; operands through the relation; case bodies transformed as kernels | interface preservation (Section 2.2 and rule C1) |
| `qstack.decode`, pre-existing | the same decode: symbol and arity unchanged, operands through the relation | interface preservation (Section 2.2 and rule C1) |
| `qstack.return` | the return of the corresponding values | discharges the output side of the kernel square (Section 4.1): returned qubits related by `R_qubit`, returned bits by `R_bit` |
| fresh allocation | the expanded fresh `|0⟩` qubits followed by a preparation fragment | the preparation implements the encoding on the allocated block: it maps the physical `|0…0⟩` to `V|0⟩` |

Fresh allocation appears in the table even though it is not an operation: allocation lives in the kernel's entry block, so it is easy to omit, and it is where an encoding pass owes the preparation of the logical `|0⟩` state. A pass whose relation is the identity owes nothing there.

Two asymmetries make the table sound. A replacement may introduce measurements freely, because a measurement carries no hidden state; it may never add a use of a pre-existing callback, because a callback does (Section 2.2). And only the `qstack.measure` row hands a new bit out of its fragment: a fragment replacing a unitary consumes every bit it creates, which is what keeps branch probabilities out of every obligation in the table.

**Cacho rewrites.** The table replaces one operation at a time. A pass may also rewrite many unitaries to many: `S;S → Z`, `X;X → ` nothing, `CX 1,2; CX 2,1; CX 1,2 → SWAP 1,2`. The unit of such a rewrite is a cacho: a consecutive run of unitaries inside one kernel body. A cacho never crosses an anchor, meaning any measure, call, select, decode, or return; those operations stay frozen by their own table rows, which is what keeps every cacho purely unitary and every callback trace untouched (Section 2.2). The question of scope answers itself through the kernel model: a select case is a kernel, so its body breaks into cachos like any other, and a whole kernel body is just the maximal cacho when the body contains only unitaries. To a compiler reader these are certified peephole rewrites, with the anchors sizing the window instead of a fixed gate count.

Because fragment boundaries inside a unitary run are not recoverable from the module pair (Section 4.2), a cacho rewrite must carry a certificate: the claimed rule together with the source and target cacho boundaries at every site where it is applied. The obligation is that both cachos implement the claimed common action through the representation relation on the cacho's qubit interface; for a same-representation optimization this is equality of the two cacho unitaries. The interface is the cacho's ordered qubit wires, so a rewrite that permutes wires, as the SWAP example does, is checked as part of that unitary. The certificate is a claim in the sense of Section 3.1: Section 4.2 describes the check, a false certificate is refuted, and a rewrite without one is UNSUPPORTED.

**Inlining.** A pass may replace a `qstack.call` with a copy of the callee's body as it appears in the pass input: arguments substituted for the borrowed entry values, SSA names freshened, and the callee's `allocates` merged into the caller's, with the callee's fresh entry qubits mapped to caller allocations. The rewrite must be claimed, naming the call site and the callee; Section 4.2 checks the copy syntactically, and no semantic reasoning is involved, because a direct call already denotes the callee's instrument composed at that point (Section 2.1). Inlining is exact substitution, so it is available for any callee, including one that measures or invokes callbacks: the copied callback uses execute exactly when the call would have, keeping every trace intact (Section 2.2). A call, by contrast, remains an anchor for cachos; a pass that wants to rewrite across a call boundary inlines first and rewrites in a second pass, each pass verified against its own input. A callee left unreachable by inlining may be dropped. Outlining, the inverse, has no rule in the contract (Section 3.4).

### 3.3 Callback rules

- **C1. Existing callbacks are untouchable.** For every `qstack.decode` and `qstack.select` use present in a pass input, the output must preserve the callback interface described in Section 2.2. In particular: a pre-existing selector retains its callback symbol, arity, bit operand order, case labels, and case kernel symbols; a pre-existing decoder retains its callback symbol and input arity; corresponding bit operands carry the same runtime values under `R_bit`; and each case kernel remains related to the kernel named by the same label. Case kernel bodies and kernel signatures may be transformed by the pass, but the callback-visible case map does not change. The callback is not reverified and no new contract is generated for it.
- **C2. A new decode may appear only in place of a measure.** A pass may introduce `qstack.decode` only to replace a `qstack.measure`: the replacement performs physical measurements and one fresh decode of their outcomes, and the decode's output stands for the replaced measurement's bit. This is the decode counterpart of rule C3, pinning each introduced callback kind to the one operation kind it may replace. A decode is never introduced to pre-process bits for an introduced selector; a selector is an arbitrary function of its bits, so that computation belongs inside it, which keeps every introduced callback's classical obligation standalone rather than checkable only jointly. The decoder declaration and every such new use are fresh relative to the pass input. The decoder's required behavior becomes a reported classical obligation (Section 4.3).
- **C3. A new select may appear only in place of a unitary.** A pass may introduce a `qstack.select` only to replace a unitary or identity fragment. It may not introduce a select as a replacement for an arbitrary kernel. Its selector declaration and use are fresh relative to the pass input. This keeps the quantum proof local and lets kernel correctness follow by composition. Every nontrivial case of such a select carries an error tag identifying the error it claims to correct, and a tag for an error at another point in the circuit must state that point; the no-error case implements the replaced unitary or identity directly. The tag's correction claim and the selector's required syndrome-to-case behavior are checked and reported as described in Section 4.3. The selector and its cases are fixed after introduction: every later pass must preserve them under rule C1, just as it preserves callbacks written in the original source module.
- **C4. Introduced bits are internal.** Bits introduced solely for a new decoder or local selector must not reach a pre-existing callback or `@main` result without an explicit relation that restores the source observable. This prevents a transformation from adding a new opaque classical interface.

### 3.4 Transformations outside the contract

Semantics-preserving transformations that neither decompose into the table of Section 3.2 nor arrive as claimed cacho or inlining rewrites receive UNSUPPORTED (Section 5) rather than a refutation: outlining a fragment into a new kernel, which preserves every callback trace but has no contract rule yet (it would be the syntactic inverse of inlining), and moving an operation across an anchor even where dataflow and per-callback order would permit it. Reordering within a run of unitaries is not in this list: certified, it is an ordinary cacho rewrite; uncertified, it is UNSUPPORTED. Unclaimed inlining is likewise UNSUPPORTED: the verifier does not search for body copies.

Pauli-frame tracking, deferring corrections into later measurement decoding, is different in kind. A materialized correction is a select, and removing it drops that selector's invocations, so a later pass that strips corrections is refuted by the trace rule of Section 2.2: materializing a correction is a one-way door under the current trace rule, and the deferred relational obligations of Section 6 are the planned way through it. Frame tracking is available only to the encoding pass itself, which may decline to emit the correction select and instead fold the frame into the decoders it introduces; under a qubit relation enriched with the tracked frame, that choice reduces to ordinary decoder obligations (Section 4.3). The enriched relation is deferred (Section 6).

## 4. How verification checks the contract

### 4.1 The correctness statement

The declared relation of Section 3.1 is generated by the qstack types:

```
R_qubit(ρ_L, ρ_P)  iff  ρ_P = V ρ_L V†
R_bit(b_L, b_P)    iff  b_L = d(b_P)
R_(τ1 × τ2)        pointwise
```

Here `b_P` is the tuple of physical bits on the explicit dataflow path into `d`, the decoder between physical measurement and logical consumer; for a same-representation pass, `d` is the identity on a single bit. For an introduced decoder, its required behavior is not silently trusted: it becomes a classical obligation derived from the quantum relation (Section 4.3).

Two source and compiled kernels are related when their instruments satisfy the commuting square:

```
(id_Q ⊗ d) ∘ ⟦K_P⟧ ∘ V^⊗|in|
    =
(V^⊗|out| ⊗ id_bits) ∘ ⟦K_L⟧
```

This is an equality after interpreting the two kernels through the representation relation, not a requirement that their raw result lists be equal. `V^⊗|in|` acts on the qubit systems of `in`; borrowed bits are outside `V`'s scope, since they parameterize the instrument family (Section 2.1), and the square is required per `R_bit`-related assignment. It includes returned-bit distributions and their correlations with surviving quantum outputs. It covers consumed borrows because a consumed input is present in `in` and absent from `out`; it covers escaping allocations because a returned fresh qubit is present in `out` without appearing in `in`; and it covers internal allocations because a fresh qubit that is measured stays inside the kernel denotation.

The square is the correctness statement, not the checking procedure. The verifier cannot compute `⟦K_L⟧` or `⟦K_P⟧`: a kernel's denotation depends on the registered callback implementations, which stay opaque, and the obligation holds for every registry. What verification establishes instead is that each replaced operation and its replacement change the state in the same way through the relation (Sections 4.2 and 4.3), that every pre-existing callback receives the same trace (Section 2.2), and that these local facts compose into the square (Section 4.4).

### 4.2 Recovering and checking the decomposition

The kernel square is discharged by checking the per-operation decomposition of Section 3.2. Because Section 3.3 requires everything a pass introduces to live under fresh symbols, the decomposition is recoverable from the module pair alone: operations on pre-existing symbols anchor the correspondence, and every other operation is replacement material. Symbol anchors alone do not split a run of unitaries between anchors into fragments; recovery there additionally assumes the pass emits replacements in source order, one fragment per source operation, and the cacho certificates of Section 3.2 supply the boundaries when a rewrite breaks that assumption. This is what lets verification satisfy P2, checking artifacts without trusting the pass to report what it rewrote: an anchor-recovered decomposition needs no input from the pass, and a certificate is checked before it is used.

A claimed inline is checked syntactically: the fragment standing for the `qstack.call` must be α-equivalent to the callee's body in the pass input, with arguments substituted, SSA names freshened, and the callee's allocations mapped into the caller's entry block. No semantic check is needed, since relatedness at the site follows from the composition of instruments in Section 2.1, and a later pass treats the copied operations as ordinary pre-existing operations. Like a certificate, the claim affects completeness, never soundness: a false claim is REFUTED and a missing one leaves the transformation UNSUPPORTED.

A certified cacho rewrite is checked in two steps. The claimed rule is checked once, semantically, as the per-rule form of the Section 4.1 square: `U_P ∘ V^⊗k = V^⊗k ∘ U_L`, where `U_P` and `U_L` are the unitaries the two cachos denote on their qubit interface; for identity `V` this is equality of the two, so `Z = S·S` is checked as matrices once however many sites claim it. Each claimed site is then checked to instantiate the rule syntactically. A false certificate is REFUTED and a missing one is UNSUPPORTED, so certificates affect completeness, never soundness (P2), and the semantic cost scales with cacho width rather than kernel width. The same per-rule square covers the other pass families: a decomposition is the identity-`V` instance with one-gate source cachos, and an encoding is the code-isometry instance with one-operation cachos, so all three pass families discharge P1's single obligation through the same checker.

### 4.3 Derived classical obligations

An introduced callback's required behavior is derived from the quantum relation, never trusted (P4).

For a decoder introduced under rule C2, the quantum verifier does not execute or inspect the decoder implementation. It derives and reports a finite classical obligation containing:

1. the callback symbol and input layout;
2. the reachable input bit tuples in the noiseless relation;
3. the output required for each reachable tuple; and
4. any explicitly unconstrained tuples.

A classical verifier is responsible for checking that the registered decoder satisfies that obligation for the required call histories. Until then, the quantum result is verified modulo the reported decoder obligation.

For a selector introduced under rule C3, the quantum verifier checks each tagged case in its declared reference frame. For an error `E` occurring after a replaced operation `U`, a correction case kernel `C_E` must satisfy:

```
C_E E U = U
```

Equivalently, `C_E E = I` on the image of the code space at the point where `E` occurs. For a tag naming an error at another point in the circuit, the verifier uses the corresponding conjugated relation.

From the measurement/correction structure and these tags, the quantum verifier reports the finite syndrome-to-case behavior required of the new selector. It does not inspect or run the selector's host implementation. A classical verifier later checks that deterministic stateful implementation against the reported obligation for the required call histories.

### 4.4 Composition

The following semantic facts are required for the end-to-end claim:

- **Local composition.** Related instruction replacements compose sequentially. This is what lets a newly introduced decoder or selector be justified at its replacement site rather than against an enclosing kernel.
- **Kernel calls.** If a callee kernel pair is related, replacing a `qstack.call` with the corresponding compiled call preserves the caller's relation.
- **Kernel composition.** If all local fragments in a kernel are related and every pre-existing callback interface is preserved, the source and compiled kernels are related.
- **Root adequacy.** If every reachable named kernel pair is related, all pre-existing callback uses are preserved, and every added callback obligation is discharged, the source and compiled `@main` kernels are related for the fixed callback registry and initial callback state.

These statements rely on linearity: it ensures there are no unaccounted wires, implicit copies, aliases, or silent discards between local obligations.

## 5. Verdicts and obligation handoff

Quantum verification produces one of:

- **VERIFIED**, when all quantum obligations are discharged and the pass generated no classical obligations;
- **VERIFIED MODULO CLASSICAL OBLIGATIONS**, with the finite decoder and/or selector contracts that remain to be checked;
- **REFUTED**, naming the failing operation, kernel, branch, relation, or callback interface; or
- **UNSUPPORTED**, when the transformation lies outside the supported quantum reasoning fragment (Section 3.4).

The obligation handoff to a classical verifier is part of the design boundary, but its data format, the classical verifier, and integration APIs are not fixed here.

## 6. Deliberately deferred

This document does not yet choose:

- concrete verifier algorithms, matrix/stabilizer representations, or external tools;
- the obligation data structure or pass-manager integration;
- an API through which a pass declares a representation relation or error tag;
- the parser and runtime representation of the target IR;
- the certificate data structure through which a pass names its cacho rewrites (Sections 3.2 and 4.2);
- kernel summaries: a call to a transitively unitary, non-recursive kernel may be summarized by its unitary, letting the call join a cacho rewrite without first materializing an inline; with inlining a permitted rewrite, this is a convenience, not a capability;
- the frame-enriched qubit relation for encoding passes that track Pauli frames instead of materializing corrections;
- relational obligations for trace-changing rewrites, all of one shape: a subgraph of pre-existing callbacks is replaced by fresh ones, and the obligation states that the two are equal as functions of the removed symbols, with a statelessness requirement on each removed callback. Correction-select removal is the instance with quantum content: the removed select's per-label effect on each downstream measurement is derivable from its case kernels and the linear qubit chain (conjugating each case's Pauli through the intervening Clifford gates), yielding `decoder(s, m) = m ⊕ flip(fix(s))`. Purely classical instances need no quantum reasoning: fusing the decode chains and select towers that stacked encoding passes produce, or folding a decode into the selector it feeds. Nothing about a removed callback's function is assumed; the classical verifier checks the relation between registered implementations (Section 2.2 forbids all such trace changes today); or
- noisy and fault-tolerance verification.

Those are implementation-planning work after the semantic model in this document and `DESIGN.md` has been reviewed together.

## 7. Related work and lineage

The intended architecture follows established obligation-driven and translation validation practice: an untrusted transformation produces artifacts that are checked independently, with unsupported cases reported explicitly. Relevant precedents include [Why3](https://www.why3.org/), [Alive2](https://github.com/AliveToolkit/alive2), [CompCert](https://compcert.org/), [VOQC](https://arxiv.org/abs/1912.02250), [CertiQ](https://arxiv.org/abs/1908.08963), [MQT QCEC](https://github.com/munich-quantum-toolkit/qcec), and [Stabilizer Circuit Verification](https://arxiv.org/abs/2309.08676).

qstack's distinctive requirement is to preserve opaque callback interfaces while deriving, rather than trusting, the finite classical contracts needed by newly introduced quantum/classical fragments.
