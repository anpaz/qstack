# Verifying qstack compiler passes

## 1. Goal and scope

qstack does not trust its compiler passes. Quantum programs are hard enough to validate that the compiler cannot be taken on faith, so every run of a pass produces a **witness**: a record of the transformation it performed. An independent verifier checks the source module, the target module, and the witness together; in the literature this is witness-carrying translation validation. Trust lives in the verifier, never in a pass. The executable language is the kernel-only IR specified in [`DESIGN.md`](DESIGN.md).

The goal is **semantic preservation**: for every fixed callback registry and initial host state, the target (compiled) `@main` must behave like the source `@main`, read through the representation relation induced by the pass's declared encoding isometry. Throughout this document, **source** means the pass input and **target** means its compiled output. The goal is not equality of IR: a pass may change representations, introduce internal measurements, widen target resources, and rewrite every unitary. The relation defines which externally visible behavior must survive.

Section 2 gives the semantic model, Section 3 the pass contract, Section 4 the checks, Section 5 what is deliberately deferred, and Section 6 the known limitations of the design.

### 1.1 Principles

- **P1. One semantic obligation.** Optimizations, QEC encodings, and dialect lowerings are all the same thing: preservation of the kernel's behavior modulo a representation relation.
- **P2. The pass is untrusted but cooperative.** A pass reports what it did, and everything it reports is checked before it is used. A false witness is refuted; one the verifier cannot check yields UNSUPPORTED. A witness affects what can be verified, never what counts as correct.
- **P3. Existing callbacks are interfaces.** A pass preserves every callback invocation in the source module, including the global order and multiplicity of invocations, and never reasons about a callback's host implementation.
- **P4. New callback behavior is an obligation.** When a pass introduces a decoder or selector, the verifier derives the classical behavior it must have and reports it for a classical verifier to check.
- **P5. Rules are checked; kernels are composed.** Most quantum verifiers today compare the full source and target circuits for equivalence. qstack does not, for two reasons: a kernel's behavior depends on opaque callbacks, so it cannot be computed at all, and whole-program comparison grows exponentially with program size, so it does not scale. Instead the verifier checks that each small replacement preserves the semantics of the operation it replaces, and lifts those local results by composition to `@main`. Anything that does not arrive as such replacements is UNSUPPORTED, not guessed at.
- **P6. Failures are attributable.** A refutation names the rule, site, kernel, branch, or callback interface that failed.

### 1.2 Noiseless boundary

This document verifies noiseless semantics only. It claims no fault tolerance, noise resilience, threshold, or correct behavior under a noisy syndrome-extraction circuit.

An error tag on an introduced select case has a deliberately limited meaning: the case claims to correct a named error at a stated point. The tag is specified here and in `DESIGN.md` but not yet implemented; today `qstack.select` carries no such attribute. A later noisy design may add error distributions, reachability under faults, and fault-tolerance claims; none are part of the present correctness statement.

## 2. Semantic model

### 2.1 A program is a collection of named kernels

A program is a module containing a finite collection of named kernels and callback declarations. One kernel, `qstack.kernel @main`, is the program's distinguished entry point.

`qstack.call` and `qstack.select` refer to other named kernels. Every invocation target is named in the symbol table; there are no function values or indirect calls, so every kernel reachable from `@main` is statically known.

A kernel denotes a map `⟦K⟧`: give it the state of its borrowed inputs `in`, and it describes what the kernel delivers on its qubit results `out` and bit results `bits`. A kernel that measures is probabilistic, and the map carries all of it: each possible bit outcome, its probability, and the quantum state that comes with it. In quantum information terms this map is a quantum instrument:

```
⟦K⟧ : states(in) → states(out, bits)
```

This document uses the standard definitions without developing them. What matters here is the shape: quantum and classical outputs travel in one map, so the correlations between returned bits and surviving qubits are part of what a kernel means. Borrowed bits parameterize the family, one map per assignment of their values. The instrument is what VERIFIED makes claims about: the verifier never computes one (P5), but every local check is justified by what it does to this map.

The map's boundary follows the kernel's signature. Fresh qubits from `allocates N` are not inputs: they start inside the kernel in `|0⟩`, and each is either measured during the invocation or handed out as a qubit result. Measurement outcomes consumed inside the kernel by `decode` or `select` are not outputs: they never leave the map. What crosses the boundary is exactly the declared inputs and results.

A `qstack.call` plugs the callee's map in at the call site. A `qstack.select` runs one map from its finite menu of case kernels.

### 2.2 A kernel is a dataflow graph

Each kernel body forms a separate dataflow graph. The program is therefore a collection of kernel graphs, not one whole-program graph. Verification compares each source kernel graph with its corresponding target kernel graph independently.

This graph view is not a new representation: linearity gives every qubit and bit value exactly one producer and one consumer, so the graph is already present in the kernel body, written down in sequence form.

The operations are the nodes; the SSA values are the wires. The sources are the borrowed inputs and the fresh `|0⟩` qubits; the sink is `qstack.return`. A `qstack.measure` is an interior node where a qubit wire ends and a bit wire begins. A `qstack.call` is a single opaque node; the callee's internals are not part of the caller's graph. A `qstack.select` references its case kernels, each a graph of its own.

Two kernel bodies are the same kernel when their graphs match: same nodes, symbols, attributes, and wiring. In particular, the order of two operations connected by no wire is not part of the kernel graph. This is safe in the noiseless model, where operations on disjoint qubits commute: emitting them in either order produces the same graph. Order matters only where a wire carries it, and one more wire is needed for the order that matters to callbacks.

### 2.3 One host machine and the host wire

At runtime a module runs against one fixed callback registry and one initial host state. All callbacks execute on a single deterministic, stateful host machine and may share its state: each result and the machine's next state are fixed by the current state and the received bits. A selector maps its bits to one label of a select's finite case map; a decoder maps its bits to one bit. Implementations are opaque to the compiler. The finite case map is a validation boundary: everything the selector can choose is a named kernel the verifier can inspect.

Because the host is stateful and shared, what matters semantically is the single global order of all callback invocations. The graph carries it as the **host wire**: one linear wire representing the host state, threaded through every `decode` and `select`, and through every call whose callee transitively invokes a callback (computable from the static call graph). The wire enters each kernel implicitly and leaves through its return, running from `@main`'s entry to `@main`'s return; the sequence of nodes along it is the invocation trace. Like the rest of the graph, it is derived from the IR, not printed.

The host wire tracks order, nothing more. The host state stays opaque: no rewrite is ever justified by reasoning about the wire's value, only refuted by changing its shape.

For each callback use in the source module, the target module must make the same runtime call: same symbol and declaration, same arity, bit operand order, and case map, corresponding bit values, and the same global order, multiplicity, and reachability. The compiler may not replace, wrap, drop, duplicate, retarget, or reorder such an invocation, and may not add invocations of a callback declared in the source module. It need not know the callback's answer: the same implementation and initial state run before and after compilation, so determinism gives the same results. In the graph, all of this is one statement: **the host wire's sequence of pre-existing callback nodes is preserved.**

The constraint is on the runtime trace, not the static operation count: inlining copies a callback operation without changing when it executes (a run takes the copy or the callee, never both), so it keeps the trace. A newly introduced callback needs a fresh declaration and the obligations of Section 3.4. The rule is relative to each source module: a callback added by one pass is an ordinary fixed callback for the next.

**Example: teleportation.** The module below teleports the state of a fresh qubit onto a borrowed one: `@teleport` prepares the state to send, entangles, measures both of its fresh qubits, and asks the host which Pauli fix to apply. It parses and verifies as written.

```mlir
builtin.module {
  qstack.selector @teleport_fix arity 2
  qstack.kernel @fix_i <[!qstack.qubit], [!qstack.qubit]> allocates 0 {
  ^bb0(%0: !qstack.qubit):
    qstack.return %0 : !qstack.qubit
  }
  qstack.kernel @fix_x <[!qstack.qubit], [!qstack.qubit]> allocates 0 {
  ^bb0(%0: !qstack.qubit):
    %1 = cliffords.x %0
    qstack.return %1 : !qstack.qubit
  }
  qstack.kernel @fix_z <[!qstack.qubit], [!qstack.qubit]> allocates 0 {
  ^bb0(%0: !qstack.qubit):
    %1 = cliffords.z %0
    qstack.return %1 : !qstack.qubit
  }
  qstack.kernel @fix_xz <[!qstack.qubit], [!qstack.qubit]> allocates 0 {
  ^bb0(%0: !qstack.qubit):
    %1 = cliffords.x %0
    %2 = cliffords.z %1
    qstack.return %2 : !qstack.qubit
  }
  qstack.kernel @teleport <[!qstack.qubit], [!qstack.qubit]> allocates 2 {
  ^bb0(%target: !qstack.qubit, %shared: !qstack.qubit, %source: !qstack.qubit):
    %0 = cliffords.x %source
    %1 = cliffords.h %shared
    %2, %3 = cliffords.cx %1, %target
    %4, %5 = cliffords.cx %0, %2
    %6 = cliffords.h %4
    %m0 = qstack.measure %6
    %m1 = qstack.measure %5
    %7 = qstack.select @teleport_fix(%m0, %m1) [%3] {"0" = @fix_i, "1" = @fix_x, "2" = @fix_z, "3" = @fix_xz} : (!qstack.qubit) -> !qstack.qubit
    qstack.return %7 : !qstack.qubit
  }
  qstack.kernel @main <[], [!qstack.bit]> allocates 1 {
  ^bb0(%0: !qstack.qubit):
    %1 = qstack.call @teleport(%0) : (!qstack.qubit) -> !qstack.qubit
    %2 = qstack.measure %1
    qstack.return %2 : !qstack.bit
  }
}
```

The graph reading of `@teleport`, with qubit wires solid, bit wires dotted, the host wire bold, and host nodes drawn with a double border:

```mermaid
flowchart TB
    target(["%target (borrowed)"]) --> cx1
    shared(["%shared (fresh)"]) --> h1["h"]
    source(["%source (fresh)"]) --> x1["x"]
    hostIn(["host"]) ==> sel

    h1 -- "%1" --> cx1["cx"]
    x1 -- "%0" --> cx2
    cx1 -- "%2" --> cx2["cx"]
    cx1 -- "%3" --> sel
    cx2 -- "%4" --> h2["h"]
    cx2 -- "%5" --> m1["measure"]
    h2 -- "%6" --> m0["measure"]
    m0 -. "%m0" .-> sel
    m1 -. "%m1" .-> sel

    sel[["select @teleport_fix<br/>{0: @fix_i, 1: @fix_x, 2: @fix_z, 3: @fix_xz}"]]
    sel -- "%7" --> ret["return"]
    sel == "host'" ==> ret
```

And the graph of `@main`, where the host node is the call, because its callee reaches `@teleport_fix`:

```mermaid
flowchart TB
    q0(["%0 (fresh)"]) --> tele
    hostIn(["host"]) ==> tele
    tele[["call @teleport"]] -- "%1" --> m["measure"]
    tele == "host'" ==> ret
    m -. "%2" .-> ret["return"]
```

The graphs make the model concrete:

- The sources of `@teleport` are the borrowed `%target`, the two fresh qubits, and the incoming host state; the sink is the return, which the host wire also leaves through.
- `x` and `h` share no wire, and neither do the two measures: their relative order is not part of the program, and a pass may emit either first.
- Each measure ends a qubit wire and starts a bit wire. Both bit wires flow into the select, so no measurement outcome leaves the kernel.
- The select is the kernel's only host node. Its case kernels are separate graphs referenced by label: `@fix_x` is a single `x` node between its borrowed input and its return.
- In `@main`, the call is an opaque node on the host wire while the final measure stays off it. A pass that moved or dropped the select would change the host wire's shape and be refuted; a pass that emitted the two measures in the other order would produce the same `@teleport` graph, which is no change at all.

### 2.4 Host interfaces and kernel boundaries

A program exposes behavior to the host in two places: when it delivers bits to a callback, and when `@main` returns its bit results. These are the program's **host interfaces**. At these points, target bits must equal the corresponding source bits. Existing callbacks must also preserve the symbol, declaration, bit arity and operand order, case map, order, multiplicity, and reachability required by Section 2.3. `@main` never returns qubits.

A call from one kernel to another is not a host interface. Its arguments and results remain internal to the qstack program, and the compiler may change their representation. For example, a source call that passes one qubit may become a target call that passes an encoded block of qubits. No host code observes that change.

Kernel boundaries are nevertheless **verification boundaries**. Because each source-target kernel pair is verified independently, their signatures must correspond through the representation relation: source and target qubit tuples are related by the pass's encoding applied to the appropriate representation units, while their bits are equal under `R_bit`. This allows the verifier to use a callee's result when checking its caller without inspecting the callee's graph.

A pass may therefore change internal measurement, encoding, and decoding plumbing, provided that:

- each kernel pair satisfies the representation relation at its signature;
- every existing callback receives the corresponding source bits; and
- `@main` returns the same externally visible bits.

### 2.5 The correctness statement

A pass declares one encoding isometry `V`, from the state space of an ordered source representation unit of `M` qubits to that of an ordered target unit of `N` qubits. This covers a one-to-one representation on distinct wire identities, a one-to-many code block, and a general `M`-to-`N` encoding. A pass that preserves representation declares the identity isometry. Each claim records which source and target wires instantiate the pass's fixed representation units.

Together with equality on bits, this encoding induces the **representation relation** used below. For a source tuple state `ρ_S` and its corresponding target tuple state `ρ_T`, the quantum relation induced by `V` is:

```
R_V(ρ_S, ρ_T)  iff  ρ_T = V ρ_S V†.
```

Thus the target state must lie in the image of `V`. Bits use the same relation in every pass:

```
R_bit(b_S, b_T)  iff  b_S = b_T.
```

Bits use equality because existing callbacks are opaque: changing a bit could change callback behavior. Thus every pre-existing callback must receive exactly the source bit tuple, and independent kernel checks require the same equality at every kernel boundary. Internal target measurement bits must be decoded back to this equality before crossing one.

At a kernel boundary containing `k` independent representation units, the induced encoding is `V^⊗k`. This is one pass-level `V` applied once per representation unit, not one separately declared isometry per wire or claim. It applies to the complete joint state, preserving correlations and entanglement.

#### Kernel behavior by outcome

A kernel that receives state `ρ` produces an outcome-indexed family. For each possible tuple `i` of returned bits, the family contains the corresponding returned-qubit state `ρ'_i`:

```
⟦K⟧ : ρ ↦ { (i, ρ'_i) }
```

The outcome component `ρ'_i` is the unnormalized state of the returned qubits conditioned on outcome `i`. Its trace is the probability of that outcome, and the traces of all outcome components sum to one. Measurement results consumed inside the kernel by `decode` or `select` do not appear in `i`; their effects are already included in the outcome components. This family is the concrete form of the instrument from Section 2.1.

#### When two kernels are related

Run the source kernel `K_S` on `ρ`. If its input contains `k_in` representation units, run the target kernel `K_T` on the related input `γ = V^⊗k_in ρ (V^⊗k_in)†`:

```mermaid
flowchart LR
    S(["ρ"]) -- "⟦K_S⟧" --> S2(["{ (i, ρ'ᵢ) }"])
    T(["γ = V^⊗kᵢₙ ρ (V^⊗kᵢₙ)†"]) -- "⟦K_T⟧" --> T2(["{ (i, γ'ᵢ) }"])
    S -. "R" .- T
    S2 -. "R" .- T2
```

Both kernels must return bits with the same arity and meaning, so their outcome-indexed families use the same index `i`. The target kernel's internal decoders ensure that `i` contains source-equivalent bits, not raw target measurement results.

The kernels are related if, for every input `ρ` and every returned-bit outcome `i`:

```
γ'_i  =  V^⊗k_out ρ'_i (V^⊗k_out)†
```

Here `k_out` is the number of returned representation units. In words: for each classical outcome, the target kernel's remaining quantum state must represent the source state through the pass's encoding. Because an isometry preserves trace, the two kernels also assign the same probability to that outcome.

This one equation preserves all externally visible behavior:

- returned bits have the same values and probabilities;
- the quantum state associated with each returned-bit outcome is preserved through the encoding;
- correlations among returned bits and qubits are preserved;
- callers, case maps, callbacks, and `@main` can use target results without translation; and
- pre-existing callbacks receive identical bits in the same global order, so they produce the same results and host-state evolution under Section 2.3.

The statement also covers consumed borrowed qubits and escaping fresh qubits because each `ρ'_i` contains exactly the qubit results declared by the kernel. Borrowed bits select which outcome-indexed family applies, so the equation must hold for every pair of related borrowed-bit assignments.

#### Encoded measurement and decoder obligations

The bit relation is equality, including at a measurement boundary. When a pass replaces source measurement with measurements of the represented target tuple, the target's raw measurement bits are internal. A fresh opaque decoder must turn them into the source-level bit or bit tuple that would have left the source measurement. The verifier derives this finite classical requirement from the measurement rule and reports it as an obligation; a classical verifier checks the registered decoder implementation. The decoder's required map is therefore not part of the representation relation or its declaration. For the three-qubit repetition encoding, the derived requirement is majority vote.

#### What the verifier checks

The commuting square above defines correctness; it is not the algorithm used to check a pass. The verifier cannot compute `⟦K_S⟧` or `⟦K_T⟧` directly because kernel behavior depends on opaque callback implementations, and correctness must hold for every callback registry.

Instead, the verifier checks that each witnessed replacement has the same local effect as the fragment it replaces (Sections 4.1 and 4.2), checks that the host wire is preserved (Section 2.3), and proves that those local facts compose into the square (Section 4.4).

## 3. The pass contract

### 3.1 The witness

A pass emits, alongside its target module, a witness containing:

1. its **encoding isometry**: the pass's single `V`, including the identity isometry for a same-representation pass;
2. the **rules** its sub-graph claims reference (Section 3.2);
3. the **claims**: which claim each node of the source and target modules belongs to, where an unlisted node belongs to the identity; and
4. each claim's **arguments**, such as an inline's callee or a correction case's error tags.

The witness is bookkeeping a rewrite driver records as it applies each claim, so pass authors do not write witnesses by hand. This sets the scope deliberately: qstack verifies passes built on its own pass framework, cooperative but untrusted, and does not try to reconstruct what an uninstrumented third-party pass did from the source and target modules alone.

A pass applies everything in one shot through its induced relation: an encoding pass applies its unitary rules together with the relation's measure and allocation rules, and no intermediate module ever exists to be valid or invalid. Verification sees the source module, the target module, and the witness.

A pass transforms the program kernel by kernel. The unit of compilation and verification is a pair of source and target kernel graphs, not one whole-program graph. The verifier checks each pair independently: a call remains an opaque node in the caller's graph, while its callee pair is verified separately. Section 4.4 then composes the per-kernel results into the end-to-end claim about `@main`.

This independence restricts a call to exactly two replacements: inline it, or preserve the call with the callee's transformed signature. Any other rewrite of a call would tie the caller's check to the callee's internals.

### 3.2 Claims

Every node of the source and target modules belongs to exactly one claim. A claim states how a piece of the program was transformed, and each claim type has its own check. There are three types today: identity, inline, and sub-graph. The vocabulary is closed but extensible: a new claim type, classical claims included, needs a defined check before any pass may use it (Section 5). Not every verifier backend can check every claim; Section 4.1 describes how backends are tried.

**Identity.** The node is preserved: the same operation, with every operand and result related through the relation, which under an identity relation means the same node outright. For some node kinds the relation carries extra content: a pre-existing `decode` or `select` keeps its symbol, arity, bit operand order, and case map, with bit operands related by `R_bit` and each case kernel related to the kernel named by the same label; a call keeps its callee, with the callee pair related separately (Section 4.4); a return returns the corresponding values, qubit tuples related by the appropriate tensor power of `V` and bits by `R_bit`. Case kernel bodies and signatures may be transformed by the pass, but the callback-visible interface does not change.

**Inline.** A call replaced by a copy of the callee's source body: arguments substituted for the borrowed entry values, SSA names renamed fresh, and the callee's `allocates` merged into the caller's. The check is purely syntactic, because a direct call already denotes the callee's instrument at that point. Inlining is exact substitution, so any callee qualifies, including one that measures or invokes callbacks: the copied callback uses execute exactly when the call would have, keeping the host wire intact. A pass that wants to rewrite across a call boundary inlines first and rewrites the copy in a second pass; the module between the two passes is an ordinary valid program. Because the copy is verbatim, inlining under a non-identity relation cannot typecheck (a source-representation copy cannot wire into target-representation surroundings), so inlining happens before the encoding pass or after it. A callee left unreachable may be dropped. Outlining, the inverse, has no claim type (Section 3.4).

**Sub-graph.** A sub-graph claim says that a particular region of a source kernel was replaced by a particular region of the target kernel using a verified rule. The rule and the claim play different roles:

- The **rule** is a reusable description of a permitted rewrite. It is written as a pair of small kernels: one source body and one target body, with signatures corresponding through the representation relation. These kernels are proof artifacts, not kernels invoked by the program.
- The **claim** records one concrete use of that rule. It names the source and target nodes at the replacement site and the wire renaming that makes those nodes match the rule.

The verifier checks the rule semantically once, then checks each claim by matching its nodes and wires against that rule. Many claims can therefore reuse one rule without repeating its semantic check. Writing rules as kernels also reuses the parser, linearity checks, and signature syntax already used for program kernels.

The source and target rule bodies must have the same effect through the relation. Writing `U_S` and `U_T` for their net actions, a rule with `k_in` input and `k_out` output representation units must satisfy:

```
U_T V^⊗k_in = V^⊗k_out U_S
```

For an identity relation, this is ordinary unitary equality. A rule may, for example, replace `S;S` with `Z`. Under the three-qubit repetition relation, a rule may replace one source `X` with one target `X` on each of the three corresponding target wires.

An ordinary rule's source body contains only unitaries. Its target body may allocate ancillas, measure them, and drive one fresh select, provided that no bit leaves the rule and every reachable execution path still implements `U_S` through the relation. T-injection has this shape: the target measures a prepared ancilla and uses a fresh selector to apply the correction that makes every reachable outcome implement `T`. A tagged unreachable correction case is checked by its correction identity instead (Section 4.3).

A rule body never contains a call or a pre-existing callback. A call must be inlined before a rule can see the callee's operations, and C1 keeps existing callbacks outside sub-graph claims. Rules are concrete: gate angles and other parameters are actual attributes from the site, not symbolic variables.

**The relation's own rules.** Ordinary sub-graph rules describe computations on wires that already exist. A non-identity encoding must also account for where a representation unit begins and ends, so it supplies allocation and measurement rules automatically. The pass does not write them.

The **allocation rule** establishes the relation when a fresh source representation unit is created. The target allocates the corresponding target unit and prepares it as `V|0…0⟩`. Allocation lives in the kernel's entry block rather than in an operation, but it still needs a claim because the pass must account for the preparation of every represented fresh unit.

The **measurement rule** recovers the source observable when a represented target tuple is measured. It replaces source measurement with target measurements followed by a fresh decode:

```
source:  measure one qubit ──────────────────────────────→ one bit
target:  measure the target tuple → fresh decode ────────→ one bit
```

The raw target measurement results remain inside the rule. The bit that leaves must equal the source measurement result. The fresh `qstack.decoder` callback remains opaque; the verifier derives and reports the finite behavior it must have for classical discharge under Section 4.3. This is the only rule that hands out a newly created bit, which keeps `R_bit` equal at every kernel and host boundary.

For example, an encoded transformation of

```
allocate → X → measure → return
```

is covered by four claims: the relation's allocation rule prepares the target block, an ordinary sub-graph rule replaces `X`, the relation's measurement rule measures and decodes the block, and an identity claim preserves the return. The ordinary rule explains the computation inside the representation; the relation's rules establish that representation at allocation and recover the source bit at measurement. An identity-relation pass needs neither relation rule because those endpoints do not change representation.

Two asymmetries keep these claims sound. A target rule may introduce measurements because measurements carry no hidden host state, but it may not introduce a use of a pre-existing callback, which may be stateful. And except for the relation's measurement rule, every claim must consume any bits it creates.

### 3.3 Callback conditions

Conditions on the witness; Section 4 rejects one that violates them.

- **C1. Existing callbacks are untouchable.** Every pre-existing `decode` and `select` node belongs to an identity claim or an inline copy, and to nothing else. No rule contains a pre-existing callback, so no sub-graph claim can touch one. Case kernel bodies may be transformed, but the callback-visible case map does not change, and the callback is not reverified.
- **C2. A new decode appears only in the relation's measure rule.** Its output stands for the replaced measurement's bit. A decode is never introduced to pre-process bits for an introduced selector: a selector is an arbitrary function of its bits, so that computation belongs inside it, keeping each introduced callback's obligation standalone. The declaration and every new use are fresh relative to the source module.
- **C3. A new select appears only inside a rule's target body.** Its selector declaration and use are fresh. A case reachable in the noiseless semantics is justified by the rule's branch check; an unreachable case, as a QEC correction case is, carries an error tag naming the error it claims to correct (a tag for an error at another point must state that point) and is checked by its correction identity. Once introduced, the selector and its cases are fixed: later passes preserve them under C1 like any other callback.
- **C4. Introduced bits are internal.** Bits created for a new decoder or selector must not reach a pre-existing callback or a `@main` result without an explicit relation restoring the source observable. A transformation may not add a new opaque classical interface.
- **C5. Introduced callbacks are isolated.** An introduced callback's invocations land between pre-existing ones in the global trace, and would perturb them if the new implementation touched shared state. Its reported obligation therefore includes isolation: the implementation must realize its contract without reading or writing state any other callback observes.

### 3.4 Transformations outside the contract

A transformation the witness cannot express gets UNSUPPORTED rather than a refutation. Today that includes outlining a fragment into a new kernel (the inverse of inlining, with no claim type yet) and any rewrite of a source region containing a measurement or callback, which only the identity claim and the relation's measure rule may touch. Reordering two operations connected by no wire is not on this list, because it is not a transformation: the source and target modules have the same graph. Moving a pre-existing callback along the host wire is a shape change and is refuted. The verifier never searches for unwitnessed correspondences: a rewrite absent from the claims is UNSUPPORTED even if it happens to be correct.

**Example: Pauli-frame tracking.** An encoding pass may try to defer Pauli corrections into later measurement decoding instead of materializing them with `qstack.select`. The current relation cannot represent the tracked frame, so such a transformation is UNSUPPORTED; it requires the frame-enriched qubit relation deferred in Section 5. A later pass also cannot remove an already materialized correction select: doing so changes the host wire and is REFUTED.

## 4. How verification checks the witness

### 4.1 Checking rules

Before a rule can justify any claims, the verifier checks the semantic obligation from Section 3.2. For a unitary rule, it checks `U_T V^⊗k_in = V^⊗k_out U_S`, using gate matrices supplied by the dialect definitions.

If the target body performs internal measurements, the verifier checks every reachable outcome separately. Each outcome must implement the same source action through the relation. This check also derives the outcome-to-case behavior required of the rule's fresh selector. Tagged unreachable correction cases are checked separately under Section 4.3.

To discharge these obligations, the verifier tries the available backends in turn: dense matrices for small rules, stabilizer methods for Clifford rules, and external equivalence checkers for larger ones. A backend either verifies, refutes, or declines. The first definitive answer wins: a verification from any sound backend suffices, a refutation is final and refutes the pass no matter how many claims use the rule, and if every backend declines, the result is UNSUPPORTED, naming the rule. Some backends need the relation in a specific form, such as an encoding given by its stabilizer generators; that side data and the integration API are deferred (Section 5).

### 4.2 Checking the claims

The claims are checked structurally against both graphs:

1. **Partition.** Every node of the source and target modules belongs to exactly one claim; unlisted nodes to the identity. No node is shared.
2. **Sites.** Each sub-graph site holds together: no path leaves the site and re-enters it through an outside node. This is what lets the site stand alone as one action.
3. **Instantiation.** Each sub-graph site matches its rule's source body up to wire renaming, and its replacement matches the target body under the same renaming. An inline's copy must be the callee's source body with arguments substituted and names renamed. An identity claim on a callback must carry the unchanged symbol, arity, operand order, and case map. Freshness (C2, C3) is checked against the source module's symbols.
4. **Remainder and host wire.** The rest of the two graphs must agree: identity nodes correspond exactly, and the host wire's sequence of pre-existing callback nodes is identical on both sides, with introduced callbacks appearing only inside their own claims.

Every step is syntactic. A witness that makes a false statement, such as a site that does not match its rule, is REFUTED; one that is merely silent about a changed region is UNSUPPORTED. Either way the failing rule, site, or node is named.

### 4.3 Derived classical obligations

An introduced callback's required behavior is derived from the quantum relation, never trusted (P4).

For a decoder introduced by the relation's measure rule, the verifier does not execute or inspect the implementation. It derives and reports a finite obligation: the callback symbol and input layout, the reachable input tuples in the noiseless relation, the required output for each, any explicitly unconstrained tuples, and the isolation requirement of C5. A classical verifier checks the registered decoder against it; until then, the quantum result is verified modulo the reported obligation.

For a selector introduced by a rule, the verifier derives the outcome-to-case behavior required on every reachable branch (Section 4.1) and checks each tagged unreachable case at its declared point. For an error `E` occurring after a replaced operation `U`, the correction case kernel `C_E` must satisfy:

```
C_E E U = U
```

Equivalently, `C_E E = I` on the image of the code space where `E` occurs; a tag naming an error at another point uses the correspondingly conjugated relation. From the measurement structure and the tags, the verifier then reports the finite syndrome-to-case behavior required of the selector, with the isolation requirement of C5, for a classical verifier to check against the registered implementation.

### 4.4 Composition

The end-to-end claim rests on these facts:

- **Local composition.** Related replacements compose sequentially, so an introduced decoder or selector is justified at its site rather than against an enclosing kernel.
- **Kernel calls.** If a callee pair is related, the corresponding target call preserves the caller's relation.
- **Kernel composition.** If all claims in a kernel are related and the host wire is preserved, the source and target kernels are related.
- **Root adequacy.** If every reachable kernel pair is related, all pre-existing callback uses are preserved, and every added obligation is discharged, the source and target `@main` are related for the fixed registry and initial host state.

These rely on linearity and the host wire: together they leave no unaccounted wires, copies, discards, or unordered host interactions between local obligations.

### 4.5 Verdicts and obligation handoff

Quantum verification produces one of:

- **VERIFIED**: all quantum obligations discharged, no classical obligations generated;
- **VERIFIED MODULO CLASSICAL OBLIGATIONS**, with the finite decoder and/or selector contracts still to be checked;
- **REFUTED**, naming the failing rule, site, kernel, branch, relation, or callback interface; or
- **UNSUPPORTED**, when a rule exceeds every backend or the transformation lies outside what the witness can express.

The handoff to a classical verifier is part of the design boundary; its data format and integration APIs are not fixed here.

## 5. Deliberately deferred

This document does not yet choose:

- concrete rule-checking backends and the API that selects one per rule, including per-backend side data such as an encoding given by its stabilizer generators;
- the witness serialization: rule format, claim encoding, claim arguments;
- additional claim types beyond identity, inline, and sub-graph, including classical claims over the decode and select structure;
- the classical obligation data structure and pass-manager integration;
- an API through which a pass declares its encoding isometry or error tags;
- channel-valued rules: rules whose source body contains a measurement, or whose bodies denote an instrument rather than a single unitary, checked as channel equivalence; today the source body is unitary, every declared rule denotes one unitary, and a bit that must survive a rewrite is owned by the relation's measure rule;
- kernel summaries: a call to a transitively unitary, non-recursive kernel summarized by its unitary, letting the call join a rule site without inlining first;
- the frame-enriched qubit relation for encoding passes that track Pauli frames instead of materializing corrections;
- relational obligations for trace-changing rewrites, all of one shape: a subgraph of pre-existing callbacks is replaced by fresh ones, with the obligation that the two are equal as functions of the removed symbols and a statelessness requirement on each removed callback. Correction-select removal is the instance with quantum content (yielding `decoder(s, m) = m ⊕ flip(fix(s))` by conjugating each case's Pauli through the intervening Cliffords); fusing stacked decode chains and select towers is purely classical. Section 2.3 forbids all such trace changes today; or
- noisy and fault-tolerance verification.

Those are implementation-planning work after this document and `DESIGN.md` have been reviewed together.

## 6. Known limitations

These are downsides of the architecture itself, not missing features: each one is the price of a decision this document defends, and the first three can be softened while the last cannot.

- **Calls are optimization fences.** A rewrite spanning a call boundary, such as a gate at the end of a callee cancelling a gate after the call site, is invisible to every claim type: rules cannot see into an opaque node, and identity keeps the call as is. The workaround is staging: inline in one verified pass, rewrite the copy in the next. Kernel summaries (Section 5) will recover the transitively-unitary case without inlining.
- **Inlining is blunt and one-way.** It duplicates the callee's body per call site, there is no outlining claim to fold structure back, and a recursive kernel can never be fully inlined, so a recursive call boundary is a fence nothing removes.
- **No retargeting.** An identity claim keeps the callee symbol, so a pass cannot specialize a kernel for some call sites, merge duplicate kernels, or change a callee's signature. This is the deepest of the three call limitations, because it cannot be fixed with a better claim type: every obligation in this design has the shape "this pass transformed this kernel correctly," while retargeting needs "these two kernels are equivalent," an equivalence between independently written kernels, which is exactly the whole-instrument comparison P5 refuses. The one cheap special case is retargeting to a syntactically identical kernel, which a future claim could check like an inline copy; the general case is out of reach by design.
- **No context-sensitive correctness.** Each kernel pair must satisfy the square for every input state, because callees are verified in isolation. A rewrite that is correct only for the states a caller actually supplies, for instance a callee that always receives `|0⟩`, is refuted or unsupported even when the whole program would be fine. Whole-program verifiers can accept such rewrites; this design trades them away for per-kernel cost and attribution, and no staging recovers them.

## 7. Related work and lineage

The design is witness-carrying translation validation: an untrusted transformation produces a target module and a witness that an independent checker validates, with unsupported cases reported explicitly. Relevant precedents include [Why3](https://www.why3.org/), [Alive2](https://github.com/AliveToolkit/alive2), [CompCert](https://compcert.org/), [VOQC](https://arxiv.org/abs/1912.02250), [CertiQ](https://arxiv.org/abs/1908.08963), [MQT QCEC](https://github.com/munich-quantum-toolkit/qcec), and [Stabilizer Circuit Verification](https://arxiv.org/abs/2309.08676).

qstack's distinctive requirement is to preserve an opaque, stateful host interface while deriving, rather than trusting, the finite classical contracts needed by newly introduced quantum/classical fragments.
