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
- [x] Add the gate-level neutral-atom ISA dialect (`RZ`, `CZ`, `SX`) and
      Cliffords-to-atoms lowering after Phase E decoupling.
- [ ] Port phase-flip repetition-3 lowering.
- [ ] Demonstrate bit-flip plus phase-flip composition as the Shor code.
- [x] Port the Steane-code pass and decoder.
- [x] Add semantic-preservation tests across ISA and QEC pipelines.

### Phase E: Decouple ISA semantics from the evaluator

Gate semantics and surface gate recognition are currently hardcoded in Python
tables. This is workable for the prototype but does not yet realize the
per-dialect extensibility described in `DESIGN.md`.

- [x] Define a dialect-level mechanism for runtime semantics and static gate
      metadata.
- [x] Make surface include files select ISA dialects and provide gate
      declarations.
- [x] Resolve surface gates through the selected ISA instead of global
      hardcoded tables.
- [x] Decide how parameterized gate attributes expose runtime matrices.
- [x] Model `Machine` as a hybrid quantum machine composed of a QPU and CPU:
      QPU owns quantum state; CPU owns classical state and evaluates
      `select`/`decode`.
- [x] Keep MLIR module walking in `ModuleEvaluator` so execution and future
      compiler-pass validation can share traversal-oriented infrastructure.
- [ ] Add an external dialect registration/discovery mechanism so packages
      outside `qstack` can provide ISA dialects and include files.
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

## 6. Runtime QPU extensibility and STIM integration

The runtime now has the right conceptual split for backend selection:
`Machine` owns a QPU and CPU, while `ModuleEvaluator` owns MLIR walking and
SSA/control-flow state. The next step is to make the QPU side extensible and
teach the default machine to pick STIM for Clifford-only modules.

### Phase F.1: Stabilize the QPU interface

- [x] Introduce a structural `QPUProtocol` or abstract base class with the
      current evaluator-facing methods:
      `restart`, `allocate`, `release`, `measure`, and a gate-application hook.
- [x] Keep `StateVectorQPU` as the renamed/current implementation of today's
      `QPU`, preserving support for arbitrary unitary matrices and
      `NoiseChannel`.
- [x] Change `Machine(..., qpu=...)` so callers can select `"auto"`,
      `"statevector"`, `"stim"`, or provide their own QPU instance. Reject
      ambiguous combinations such as both a user-supplied QPU and `noise`.
- [x] Keep `machine.qpu` public and concrete enough for tests/notebooks, but
      type it against the protocol so external QPUs are first-class.

### Phase F.2: Make gate dispatch backend-aware

- [x] Replace evaluator calls of `qpu.apply_unitary(name, unitary, qubits)` with
      `qpu.apply_gate(GateApplication(op, qubits))`.
- [x] Keep matrix-oriented execution in `StateVectorQPU`, which calls
      `op.unitary()` and preserves support for `apply_unitary`.
- [x] Preserve the current two-qubit wire-order convention in `StateVectorQPU`,
      while `StimQPU` receives operation-order qubits directly.

### Phase F.3: Mark and detect Clifford-compatible modules

- [x] Use dialect membership rather than STIM metadata: executable
      `cliffords.*` gates are STIM-compatible; other executable
      `UnitaryGateOp`s are not.
- [x] Require Clifford-equivalent non-canonical gates such as Toy gates to be
      lowered to the Clifford dialect before STIM auto-selection.
- [x] Add `qstack.runtime.analysis.is_stim_compatible(module)` and
      structured diagnostics for the first incompatible executable gate.

### Phase F.4: Implement `StimQPU`

- [x] Add `stim` as a required dependency, matching the runtime's required
      simulator dependencies.
- [x] Implement `StimQPU` with the same allocation/free-list semantics as the
      state-vector QPU.
- [x] Map qstack Clifford ops to native STIM operations and map
      `qstack.measure` to Z-basis measurement with release/reset behavior that
      matches today's QPU contract.
- [x] Handle seeding deterministically enough for reproducible tests. If STIM's
      exact seed semantics differ from the state-vector simulator, document the
      reproducibility contract at the QPU boundary instead of promising
      cross-backend identical random streams.
- [x] Initially reject arbitrary `NoiseChannel` on `StimQPU`. Add Pauli/STIM
      noise support later as a separate backend capability rather than forcing
      Kraus noise through a stabilizer simulator.

### Phase F.5: Default backend selection

- [x] Add a `qpu="auto" | "statevector" | "stim"` selector to `Machine`, with
      `"auto"` as the default.
- [x] In `"auto"`, choose `StimQPU` when `is_stim_compatible(module)` is true
      and no legacy `noise=` argument is present; otherwise choose
      `StateVectorQPU`.
- [x] In explicit `"stim"`, fail fast with a clear diagnostic if the module or
      options are unsupported. Do not silently fall back when the user asked for
      STIM.
- [x] In explicit `"statevector"`, preserve today's behavior exactly.
- [x] If a user supplies `qpu=...`, skip automatic selection entirely and pass
      the supplied QPU through to `ModuleEvaluator`.

### Phase F.6: Tests and examples

- [x] Unit-test backend selection for Clifford-only, non-Clifford, explicit
      STIM, explicit state-vector, and user-supplied QPU cases.
- [x] Add a fake QPU test double proving `Machine` and `ModuleEvaluator` honor
      externally supplied QPUs.
- [x] Add parity coverage through the existing full MLIR suite, including Bell,
      teleportation, recursive `prepare_one`, repetition-3, and Steane
      Clifford workflows under auto-selected STIM where compatible.
- [x] Add negative tests for parameterized/non-Clifford gates and legacy noise.
- [ ] Update notebook/runtime docs to explain that Clifford-only programs use
      STIM automatically, while arbitrary unitaries continue to use the
      state-vector backend.

## 7. Recommended next milestone

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
