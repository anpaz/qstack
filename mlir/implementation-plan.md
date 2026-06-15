# qstack MLIR Implementation Plan

This document tracks the work required to implement
[DESIGN.md](DESIGN.md). It distinguishes the core qstack IR from the surface
language and from parity with the original Python prototype. Those are related
goals, but they are not the same milestone.

## 1. Implementation decisions already made

The running rationale lives in [implementation-notes.md](implementation-notes.md).
The most important decisions are:

1. **Use xdsl as the MLIR substrate.** The implementation is MLIR-style IR in
   Python rather than upstream MLIR Python bindings.
2. **Use `qstack.invoke` instead of `func.call_indirect`.** xdsl does not ship
   an indirect-call op in its `func` dialect. `qstack.invoke` has the same role
   and semantics as the op spelled `func.call_indirect` in `DESIGN.md`.
3. **Represent kernel borrows as captures.** `qstack.kernel` has no qubit
   operands. Its body captures enclosing SSA values, and linearity forces each
   captured qubit to be threaded back as a trailing kernel result.
4. **Use a hand-rolled Lark parser.** The reference `openqasm3` parser rejects
   allocating qubits inside `def`, which is required for recursive allocating
   subroutines such as `prepare_one`.
5. **Use a fixed-wire emulator.** One simulator instance owns a free-list of
   physical wires. Kernel allocation acquires wires; measurement resets and
   releases them.

## 2. Current implementation status

### 2.1 Core IR foundation: implemented

- `!qstack.qubit` and `!qstack.bit`.
- `qstack.kernel`, `qstack.measure`, and `qstack.return`.
- `qstack.select`, `qstack.decode`, and `qstack.invoke`.
- Core linearity checks for qubit and bit SSA values.
- Kernel checks for bits-equal-allocations, bits-before-qubits result order,
  and matching `qstack.return` types.
- Minimal Clifford and toy ISA dialects.
- Emulator support for kernels, nested kernels, `func.call`, selection,
  invocation, decoding, toy gates, Clifford gates, and depolarizing noise.
- Host-language callback registry and notebook integration.

### 2.2 Demonstrated end-to-end workflows: implemented

- Bell-state execution.
- Biased Bell execution through the toy ISA.
- Recursive `prepare_one` execution through `qstack.select`.
- Teleportation with selector-driven correction.
- Toy-to-Cliffords lowering.
- A narrow repetition-3 prototype for simple single-qubit programs.

### 2.3 Important qualification

The foundation is working, but `DESIGN.md` is **not yet fully implemented**.
The current repetition-code pass and surface lowering are prototypes with
documented restrictions. Notebook parity is a useful smoke test, not a
completion criterion for the design.

The `compile_rep3` path is now a stable module-to-module rewrite over explicit
SSA maps. It supports the recursive `prepare_one` workflow, selector and
continuation preservation, and repeated application. Allocating kernels nested
lexically inside another kernel remain a deliberate rejection until the pass
can restructure the enclosing kernel while keeping decoders at function scope.

## 3. Work required to complete DESIGN.md

### Phase A: Complete the module-level verifier

The verifier currently enforces linearity and kernel signatures. Add the
remaining module-level rules described in `DESIGN.md`:

- [ ] Verify that every `qstack.measure` appears inside a `qstack.kernel` with
      at least one allocation.
- [ ] Verify that every kernel entry-block argument has type `!qstack.qubit`.
- [ ] Verify that each kernel body performs exactly as many direct
      `qstack.measure` operations as it has allocations. Nested kernels satisfy
      their own count independently.
- [ ] Verify that every `qstack.select @sym` resolves to a body-less
      `func.func private` carrying `qstack.selector`.
- [ ] Verify selector named operands against the selector declaration.
- [ ] Verify that every selector continuation symbol resolves and that every
      menu entry has the declared function type.
- [ ] Verify that every `qstack.decode @sym` resolves to a body-less
      `func.func private` carrying `qstack.decoder`.
- [ ] Verify decoder arity and signature:
      `(!qstack.bit x k) -> !qstack.bit`, with `k >= 1`.
- [ ] Verify `qstack.invoke` operand and result types against its function-typed
      callee.
- [ ] Verify qstack-aware `func.func` boundaries: qubit conservation and no
      top-level `qstack.measure`.
- [ ] Add negative tests for every rule.

### Phase B: Replace the repetition-code prototype with a real QEC rewrite

The current `compile_rep3` pass only supports a small top-level subset. Rebuild
it as a module-to-module transformation over explicit SSA maps rather than
attaching ad hoc `rep3_triple` attributes to SSA values.

- [x] Stop mutating source blocks while constructing the destination module.
- [x] Rewrite all single-qubit Clifford gates transversally.
- [x] Rewrite `cx` and `cz` transversally.
- [x] Rewrite nested pure-unitary kernels recursively.
- [ ] Restructure allocating kernels nested inside another kernel so inserted
      decoders remain at function scope.
- [x] Widen `func.func` signatures mechanically.
- [x] Rewrite `func.call`, `qstack.select`, and `qstack.invoke` signatures and
      operands while preserving selector symbols and continuation menus.
- [x] Expand each logical measurement into three physical measurements and
      insert `qstack.decode @majority_vote` at function scope.
- [x] Add the `@majority_vote` decoder declaration to transformed modules when
      needed.
- [x] Preserve pre-existing decoder and selector declarations unchanged.
- [x] Verify the transformed module before returning it from the pass.
- [x] Test the `prepare_one` program after encoding.
- [x] Test pass composition by applying repetition-3 twice.

This phase is the first real demonstration of the design thesis: a QEC pass
must preserve the logical callback interface while widening quantum dataflow.

### Phase C: Introduce a proper pass abstraction

The current `BaseOpRewriter` is sufficient for one-to-one toy gate rewrites but
not for QEC rewrites that widen signatures and coordinate symbol-level
changes.

- [ ] Define a pass interface with module-level setup, symbol rewriting,
      recursive region rewriting, and post-pass verification.
- [ ] Keep local gate rewrite helpers, but do not force QEC passes into a
      handler-only shape.
- [x] Remove or fold the experimental duplicate
      `rep3_trivial_classbased.py`.
- [ ] Record whether xdsl's rewrite infrastructure can replace the local
      traversal helper cleanly.

### Phase D: Port the remaining compiler stack

The original Python prototype contains passes and ISAs not yet represented in
the MLIR implementation.

- [x] Add the H2 ISA dialect and emulator semantics.
- [x] Port Cliffords-to-H2 lowering.
- [ ] Add the atoms ISA dialect and lowering if it remains part of the target
      design.
- [ ] Port phase-flip repetition-3 lowering.
- [ ] Demonstrate bit-flip plus phase-flip composition as the Shor code.
- [x] Port the Steane-code pass and decoder.
- [x] Add semantic-preservation tests across ISA and QEC pipelines.

### Phase E: Decouple ISA semantics from the emulator

Gate semantics and surface gate recognition are currently hardcoded in Python
tables. This is workable for the prototype but does not yet realize the
per-dialect extensibility described in `DESIGN.md`.

- [ ] Define a dialect-level mechanism for emulator semantics and static gate
      metadata.
- [ ] Make surface include files select an ISA and provide gate declarations.
- [ ] Resolve surface gates through the selected ISA instead of global
      hardcoded tables.
- [ ] Decide how parameterized gate attributes expose runtime matrices.
- [ ] Add Pauli noise parity if it is still required from the original stack.

## 4. Surface-language work

The current parser intentionally implements `QSTACKQASM 0.1`, a small
qstack-owned language sufficient for the ported notebooks. It is **not** the
strict OpenQASM 3.0 subset described in
`docs/superpowers/specs/2026-05-22-openqasm-surface-design.md`.

Before expanding the frontend, choose and document one position:

- [ ] Keep `QSTACKQASM` as a qstack-owned OpenQASM-like surface language and
      revise the surface spec accordingly; or
- [ ] Restore the OpenQASM 3.0-subset goal and define exactly which syntax
      extensions are accepted beyond stock OpenQASM.

After that decision, implement the chosen v1 surface contract:

- [ ] Enforce one `qreg` allocation per `def` and at top level.
- [ ] Enforce bit single-write and single-read rules with clear diagnostics.
- [ ] Reject operating on measured qubits with clear diagnostics.
- [ ] Lower plain decoder calls to `qstack.decode`.
- [ ] Support declared `def -> bit` and fixed-size `def -> bit[k]` returns.
- [ ] Support pure `gate` declarations and calls.
- [ ] Resolve and validate `include` files and ISA selection.
- [ ] Add `if/else`, `default`, compile-time `for`, and bit-conditioned
      `while` lowering if they remain in the v1 surface contract.
- [ ] Add gate modifiers if they remain in the v1 surface contract.
- [ ] Add `qstack_aux.reset` and `qstack_aux.barrier` if they remain in v1.
- [ ] Add annotations and syntax synonyms only after the core surface is
      stable.

## 5. Documentation and cleanup

- [ ] Update `implementation-notes.md`: dependency pinning is complete in
      `pyproject.toml`; record the implemented `QSTACKQASM` decision.
- [ ] Update `DESIGN.md` examples to spell `qstack.invoke`, or explicitly keep
      `func.call_indirect` as substrate-neutral pseudocode.
- [ ] Remove stale phase comments from files whose later phases have landed.
- [ ] Keep [POSITIONING.md](POSITIONING.md), `DESIGN.md`, the surface spec, and
      this implementation plan aligned.
- [ ] Add a short extension guide for new ISA dialects and QEC passes.

## 6. Recommended next milestone

The original repetition-3 milestone is complete:

```text
prepare_one
    -> repetition-3 QEC pass
    -> verified transformed module
    -> emulator execution
    -> repetition-3 applied a second time
    -> verified transformed module
    -> emulator execution
```

This now exercises explicit decoders, unchanged selectors, continuation
preservation, QEC composition, and linear SSA verification.

The next milestone is to complete Phase A and then decide whether allocating
kernels nested lexically inside another kernel are legal IR. If they are, the
QEC pass needs a kernel-splitting or lifting transformation that preserves the
function-scope decoder rule.
