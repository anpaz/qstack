# qstack Verification Design

**Status:** Draft v1
**Date:** 2026-06-17
**Companions:** [DESIGN.md](../DESIGN.md) (IR), [POSITIONING.md](../POSITIONING.md) (thesis),
[implementation-plan.md](implementation-plan.md) (substrate status)

This note fixes the design of the verification layer before any code is written, the way DESIGN.md fixed the IR. It
covers what we check, the semantic object we check against, the shape of a QEC "package," the checker API, and the
milestone sequence. Scope for v1 is the **stabilizer (Clifford) fragment**; the non-Clifford story is deferred (§8).

## 1. Strategy

The generals proposal splits verification two ways: per-run **translation validation** (check this input/output pair is
equivalent) and once-and-for-all **instruction-level proofs** (prove a handler preserves meaning, then lift by forward
simulation). We build the **translation-validation checker first**, for three reasons:

1. It is a decidable equivalence check, not a theorem, so it is buildable now.
2. It produces immediate value: it validates the rep3, Steane, and H2 passes that already exist, replacing today's
   `2^n` emulation-and-compare tests with poly-time stabilizer checks.
3. It forces us to build the logical-action core that the later instruction-level proofs and the parametric theorem
   will reuse.

The parametric-over-the-code theorem (the "swappable package" claim) is Track 2, after the checker works.

## 2. What we check

For a compiler pass `P` applied to a source region `src` producing `tgt = P(src)`, against a QEC package with encoder
action `enc` and decoder spec `dec`, the checker confirms:

> the logical action of `tgt`, read through the package, equals the logical action of `src`.

Concretely, in the Heisenberg/stabilizer picture, for every generator `L` of the logical Pauli frame:

```text
tgt   maps   enc(L)   to   enc( action_src(L) )      (mod stabilizers, up to sign)
```

plus a coherence condition at measurement boundaries: the classical decoder spec computes the eigenvalue of the named
logical operator from the physical outcomes. For a trivial package (an ordinary non-QEC pass), `enc` is the identity and
this reduces to plain logical-action equality of `src` and `tgt`.

This is the logical-action method of *Stabilizer Circuit Verification* (Kliuchnikov, Beverland, Paetznick). We implement
it; we do not reinvent it.

## 3. The semantic object: logical action

The thing correctness is stated against is the **logical action** of a region, not its state-vector behavior. For the
Clifford fragment of the IR, the logical action of a `func.func` or region over `n` qubits is:

- how it transforms each input Pauli operator (the symplectic/tableau part), and
- how each measurement outcome is produced as an F2-linear (parity) function of input Paulis and fresh randomness, and
- how `qstack.select` branch choices depend on the parity of prior bits.

The restriction that classical control depends only on **parity (XOR)** of prior measurement bits is what keeps the
comparison decidable over F2. This is a real constraint on the fragment we verify, and it matches how `qstack.decode`
and `qstack.select` are used in the QEC passes (majority vote, syndrome parity, conditional Pauli corrections).

This logical-action denotation is the v1, stabilizer-specialized form of the generals' "single formal semantics
independent of abstraction layer." A full density-matrix semantics is only needed for the non-Clifford stretch goal.

## 4. The QEC package (interface `I`)

A package is the swappable object a code supplies. As a concrete data structure it carries:

- **`n_physical` per logical qubit** (1 for a trivial package, 3 for rep3, 7 for Steane).
- **Stabilizer group `S`** (the physical operators fixing the codespace).
- **Logical operator action `enc`**: for each logical generator (`X_L`, `Z_L`, per logical qubit), its physical Pauli
  representative `enc(L)`. This is the encoder's Heisenberg action and the only part of the encoder the checker needs.
- **Decoder spec `dec`**: an F2 model of what the classical decoder is *supposed* to compute (e.g. majority vote =
  parity-corrected logical bit on the correctable set). This is a specification, not the decoder body.

The decoder body stays opaque host-language code (the trust boundary). The checker uses `dec` (the spec); whether the
registered Python decoder actually meets `dec` is a separate, classical obligation. This is the verified-vs-trusted
split made concrete: the quantum side is checked against `enc`/`S`; the classical decoder spec is assumed and discharged
elsewhere.

The minimal contents of this structure, and the well-formedness conditions on it (logical operators in `N(S)`,
independent mod `S`, decoder correct on the correctable set), are the formal answer to "what makes a code correct" that
Track 2 turns into the parametric theorem.

## 5. The checker

### 5.1 Engine: Stim

Stim is the tableau/F2 engine (decision recorded; it is already cited in the generals). The qstack-specific layer is
(a) extracting a `stim.Circuit` from the Clifford fragment of a qstack region, and (b) expressing the logical-action
equivalence as **Stim flows**.

Stim's `stim.Flow` and `circuit.has_flow(...)` are exactly the right primitive: a flow is `P_in -> P_out` possibly xored
with measurement records, and `has_flow` verifies the circuit implements it, including measurement and feedback. The
logical-action check becomes: for each generator, build the flow `enc(L) -> enc(action_src(L))` (with the appropriate
measurement records for decoded outcomes) and assert `tgt_circuit.has_flow(flow)`. Equivalence of `src` and `tgt` for a
trivial package is the same check with `enc = identity`.

### 5.2 Pipeline

```text
qstack region (Clifford fragment)
   |  extract  (map Clifford ISA ops, measure, parity decode/select -> stim ops)
   v
stim.Circuit  (+ measurement record layout)
   |  build flows from the package's logical generators
   v
has_flow checks, one per generator (+ decoder coherence)
   v
pass / fail  (a validation certificate attached to the pass result)
```

### 5.3 API sketch

- `extract_circuit(region) -> (stim.Circuit, RecordLayout)` for the Clifford fragment; raises on non-Clifford or
  non-parity-control ops (clearly, so the boundary is visible).
- `Package` dataclass holding `n_physical`, `S`, `enc`, `dec` (§4).
- `validate(src, tgt, package) -> Certificate` running the per-generator `has_flow` checks plus decoder coherence.
- Wire `validate` in as an optional **post-pass certificate**, alongside the existing post-pass structural verify.

## 6. Milestones

Each milestone validates a pass that already exists, so the work ships value continuously.

- **M0 (foundation).** `extract_circuit` for a Clifford `func.func` (gates only, no measurement), and a logical-action
  equality check between two of them via Stim. Tableau-only; no package yet.
- **M1 (trivial package).** Validate **Toy -> Cliffords**. Identity `enc`, no encoding. Smallest end-to-end pipeline.
- **M2 (first real QEC).** Validate **Rep3** on `prepare_one`. Real `enc`/`S`/`dec`; the commuting-square check; first
  use of measurement + parity feedback in flows. This is the first genuine demonstration of the thesis.
- **M3 (composition).** Validate **rep3 squared**, **rep3 -> H2**, and **Steane**. The "guarantees stack" claim becomes
  a runnable demonstration.
- **Faulty passes** (generals 5.4). Build deliberately-broken rewrites (wrong decomposition, wrong syndrome circuit,
  bad encoder, gate dropped) and confirm the checker *rejects* them. This is what proves the checker has teeth; cheap
  once M1/M2 exist.

## 7. Relationship to existing code

- The passes are already per-operation handlers (rep3, Steane) and pure module-to-module rewrites, so the checker bolts
  on as a post-pass step without restructuring them.
- Today's "semantic-preservation tests" are emulation-and-compare (`2^n`). M1 to M3 replace them with poly-time flow
  checks; keep a few emulation tests as cross-checks during bring-up, then retire the rest.
- H2 note: H2 can express non-Clifford rotations, but the angles the Clifford lowering emits are Clifford instances. The
  extractor accepts only those; arbitrary-angle `rz` is a non-Clifford boundary (deliberately rejected in v1).

## 8. Boundaries and open items

- **Non-Clifford** (`T`, magic states) is out of v1. It needs a different semantic object (density-matrix or
  superoperator equivalence) and is the named stretch goal. The IR already quarantines non-Clifford cost at
  `select`/`decode` boundaries, which is where a future hybrid check would attach.
- **Decoder bodies are trusted**, checked only against the `dec` spec. Verifying a real decoder (majority vote is
  trivial; a surface-code decoder is not) against its spec is separate classical-verification work, not part of v1.
- **Parity-only classical control** is a real restriction; document clearly when a `decode`/`select` falls outside it.
- **Forward-simulation lifting** and the **parametric theorem** (Track 2) are deferred until the checker is solid.
