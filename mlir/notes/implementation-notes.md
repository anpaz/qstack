# qstack MLIR Implementation Notes

Running log of every non-trivial decision, deviation from the spec, environment quirk, or thing the user should know. Append-only; never rewrite history. Newest entries at the bottom of each section.

---

## 2026-06-07 — Repetition-3 compiler completion

10. **The repetition-3 compiler is a pure destination-building rewrite.** `compile_rep3` no longer mutates source blocks or attaches `rep3_triple` attributes to source SSA values. Each function is rebuilt into a new region using an explicit map from every source SSA value to one logical value or three physical values. The input module remains unchanged and independently verifies after compilation.

11. **Qubit widening is global; bit widening is confined to kernel boundaries.** Every `!qstack.qubit` function argument, result, call operand, call result, select continuation type, and invoke operand/result expands 1→3. Ordinary `!qstack.bit` values stay width one. A kernel bit result expands 1→3 because it represents three physical measurements; the pass immediately inserts `qstack.decode @majority_vote` after the rewritten kernel and maps downstream uses of the old bit to the decoded logical result.

12. **Callback declarations are interface boundaries.** Existing body-less `func.func private` declarations tagged `qstack.selector` or `qstack.decoder` are copied with exactly the same signature and attributes. Selector symbols and continuation dictionaries are preserved; only the function type carried by `qstack.select` widens. Non-callback function declarations widen like ordinary quantum function boundaries.

13. **`@majority_vote` is added once and validated on reuse.** The pass inserts a private `qstack.decoder` declaration with signature `(!qstack.bit, !qstack.bit, !qstack.bit) -> !qstack.bit` when it inserts its first decoder. A second repetition-3 application reuses that declaration. If the symbol already exists with a different body, tag, or signature, compilation fails with `Rep3CompileError` instead of shadowing it.

14. **The pass verifies its own output.** Before returning, `compile_rep3` runs both xdsl structural verification and `qstack_mlir.verifier.verify_module`. This makes malformed output a compiler failure rather than deferring detection to the caller.

15. **Composition behavior is decoder stacking, not decoder replacement.** On the second repetition-3 application, each first-layer physical measurement is expanded to three lower-layer measurements and decoded by a newly inserted majority vote. The first-layer majority-vote op remains unchanged and consumes those three newly decoded bits. This produces the intended 9-qubit concatenation while preserving every pre-existing callback reference.

### Known boundary

- Pure-unitary nested kernels are rewritten recursively and covered by tests.
- An allocating kernel nested lexically inside another kernel is not yet a promoted workflow. Its decoder would naturally be inserted in the enclosing kernel rather than at function scope; moving it to function scope requires restructuring or splitting the enclosing kernel. The current `prepare_one` recursion does not have this shape: it is a function call between separately scoped kernels and is fully supported.
- The state-vector simulator allocates `2 ** num_qubits` amplitudes even though the evaluator uses a free-list. Concatenated-code tests should therefore use the minimum live-wire budget: 6 wires for one repetition layer of `prepare_one`, and 18 for two layers. Passing a generously oversized wire count can make otherwise small tests extremely slow.

## Environment

- **Venv:** `/Users/anpaz/Repos/.venv/qstack` (Python 3.12.7).
- **Pinned deps (initial):**
  - `xdsl==0.64.0`
  - `openqasm3[parser]==1.0.1` (pulls `antlr4-python3-evaluator==4.13.2`)
  - `pytest==9.0.3`
- **Not yet pinned in a `pyproject.toml`** — installs are bare `pip install` so far. Pinning will happen in Phase 0.3.

---

## Phase 0 — Repo prep

### 0.4 xdsl smoke test (PASS)

- Built a tiny `foo` dialect with a custom `ParametrizedAttribute + TypeAttribute` (`!foo.t`) and two ops (`foo.make` producing the type, `foo.use` consuming it).
- Built a `ModuleOp([mk, use])`, printed, parsed, re-printed — byte-equal round-trip.
- API used:
  - `xdsl.ir.{Dialect, ParametrizedAttribute, TypeAttribute}`
  - `xdsl.irdl.{irdl_attr_definition, irdl_op_definition, IRDLOperation, result_def, operand_def}`
  - `xdsl.context.Context`, `xdsl.printer.Printer`, `xdsl.parser.Parser`
  - `xdsl.dialects.builtin.{ModuleOp, Builtin}`
- **Gotcha:** `Block` is NOT a context manager (unlike LLVM MLIR's Python bindings). You build a block by constructing its ops first and passing them to `ModuleOp([...])` (or `Block([...])`). The "insertion-point context manager" idiom from upstream MLIR doesn't apply.

### 0.5 openqasm3 probe (PARTIAL FAIL — design impact)

Two restrictions of the `openqasm3` reference parser that conflict with our surface spec:

1. **`extern selector` is a parse error** (expected — it's our one extension to the language; not in the reference grammar).
2. **`qreg` / `qubit` declarations inside a `def` are rejected** with `qubit declarations must be global`. This is enforced in `openqasm3/parser.py::visitQuantumDeclarationStatement`.

These come from the reference parser actively enforcing QASM-3 semantics, not just lossily passing the tree through.

**Impact on the surface spec:** the spec's headline `prepare_one` example puts `qreg ancilla[1];` inside `def prepare_one(qubit q) { ... }` — this is structurally rejected. Without inner `qreg`, the surface spec cannot express its central idiom (a recursive allocating subroutine), which means the spec's `def` ↔ `qstack.kernel` lowering rule (§3.2, §5.1) cannot stand on top of `openqasm3` as-is.

**Probes that DID pass:**

- `extern majority_vote(bit, bit, bit) -> bit;` — fine.
- `switch (m) { case 0 { } case 1 { x q; } }` — fine.
- `def f(qubit q) -> bit { bit m; measure q -> m; return m; }` — fine (without inner qreg).

**Available paths forward** (need user decision; recorded in §"Open questions"):

| Option                                                                                                                                                              | Effort                | What it costs                                                                                                                                                                        |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **A. Pre-process source** before `openqasm3.parse` — regex-rewrite `extern selector` to a tagged stock extern; lift inner `qreg`s to module-scope synthetic globals | Medium                | Inner-qreg lifting breaks recursion semantics (each call would re-use the same global qubits) — would force the surface spec to forbid recursive allocating subroutines. Wrong.      |
| **B. Fork the openqasm3 visitor** — vendor the `parser.py` visitor and remove the global-only-qubit check; ditto for accepting `extern selector`                    | Medium                | We own a fork of a 1k-line file from openqasm3; antlr grammar still doesn't tag `extern selector` as anything distinct, so we'd still need a pre-pass. Brittle on openqasm3 updates. |
| **C. Hand-roll parser with `lark`** over a tight grammar that matches the surface spec verbatim                                                                     | Medium-large up-front | Adds one dep (`lark`), removes `openqasm3`. We become the ground-truth for our restricted dialect, no version drift. The most spec-faithful path.                                    |
| **D. Change the surface spec** — drop inner `qreg`; allocations happen only at the top level                                                                        | Medium                | Surface spec needs revision; the heralded-prep / RUS recursive idiom dies; example `prepare_one` would have to be re-written to a non-recursive style. Highest semantic cost.        |

**Provisional recommendation:** Option C. The openqasm3 dep was attractive for "free grammar"; it turns out the grammar is too strict for the construct that motivates the whole surface design. A hand-rolled `lark` parser is bounded effort (the surface is small) and lets us own the grammar that matches our spec.

**This decision must be made before Phase 3 starts.** Phases 1 (dialect) and 2 (emulator) are independent of the parser choice and can proceed.

---

## Decisions log

1. **2026-05-28 — Parser choice for the surface language: Option C (hand-roll with `lark`).** Chosen by the user. `openqasm3` is removed from required deps in Phase 3; we'll add `lark` instead. Pre-Phase-3 todo: drop `openqasm3` from `pyproject.toml` and add `lark`. The grammar covers only the §6 accepted subset of OpenQASM 3.0 plus the `extern selector` extension.

2. **2026-05-28 — `qstack.kernel` results are _not_ segregated** at the IRDL level: a single `var_result_def()` holds bits-then-qubits. Reason: xdsl's `AttrSizedResultSegments` is heavy for what is purely a verifier invariant. The bits-first-then-qubits ordering is checked by the Phase 1.1 module-level verifier, not by IRDL. Same applies to `qstack.return` operands.

3. **2026-05-28 — `qstack.return` carries `HasParent(KernelOp) + IsTerminator` traits** so xdsl rejects it outside a kernel and as a non-last op for free. Bit/qubit count match with the enclosing kernel is again a Phase 1.1 module-level check.

4. **2026-05-28 — Assembly format experiments** wired via `assembly_format` strings on each op. Not yet exercised — Phase 1b tests round-trip through the _generic_ printer/parser (xdsl falls back automatically). Custom syntax will be validated when DESIGN.md-style textual examples become test inputs in Phase 1 Verify.

5. **2026-05-28 — `qstack.invoke` op replaces `func.call_indirect`.** xdsl does not ship an indirect-call op in its `func` dialect. Rather than vendor one, we added a small `qstack.invoke %fn(%args...) : (...) -> (...)` op with identical semantics. DESIGN.md continues to spell the site as `func.call_indirect` but the implementation will use `qstack.invoke` until upstream xdsl provides an alternative. This is a pure spelling change; the operational semantics, type system, and IR shape are unchanged.

6. **2026-05-28 — Kernel borrow semantics: block-args, not closure.** _(Superseded by Decision 7.)_ Initially: borrows surface as additional entry-block arguments alongside allocations, with the kernel op operand list recording which outer values are passed in. Replaced with the cleaner capture-based design below once we realized the operand list was redundant.

7. **2026-05-28 — Kernel has zero qubit operands; borrows are captures.** xdsl regions are not `IsolatedFromAbove` by default — the body can reference enclosing-scope SSA values directly. Combined with strict single-use linearity, this makes the explicit borrow operand list unnecessary: every captured outer qubit has its single use inside the body, and the only way for that use to be satisfied while leaving the kernel boundary linearity-clean is for the body to thread the qubit back as one of the trailing qubit results. The kernel signature becomes `() -> (bit × a, qubit × b)`, where `a = #entry-block-args` and `b = #qubit-results`. The verifier drops the borrows-count rule entirely; linearity does the work. DESIGN.md and all tests updated in the same pass.

8. **2026-05-28 — Emulator uses a free-list of physical wires over a single `qsharp.noisy_simulator.StateVectorSimulator`.** No per-kernel restart, no resize: the simulator is constructed once with `num_qubits` wires; allocations pop a free index, measurements reset the wire to `|0⟩` and push the index back. SSA threading is implemented by binding each gate result to the same physical index as its operand. Captures cost nothing extra — the captured value's SSA-to-index binding is already in `env` when the nested body runs. Phase 2 Verify (1000 shots of `prepare_one` → all `1`) passes against this design.

9. **2026-05-28 — CX/CZ qubit-order convention: `[target, control]` at `apply_operation` call sites.** Matches the existing `src/qstack/emulator.py` convention (little-endian wire indexing with control ⊗ target tensor order on the gate matrix). Verified by `test_bell_kernel_correlated` and by Phase 2 Verify.

## Open questions (for user)

_(None open.)_

---

## 2026-06-07 — Repetition-3 follow-up

- **Nested allocating kernels now fail explicitly.** Following the boundary recorded in Decision 15, `compile_rep3` raises `Rep3CompileError` when a bit-producing kernel is nested inside another kernel. This prevents the pass from silently placing a decoder inside the enclosing quantum region. Pure-unitary nested kernels remain supported.
- **Log-order note:** the detailed repetition-3 entries numbered 10–15 were added earlier in this file rather than after the previous Decisions log. They are additive history and have intentionally not been moved or rewritten, preserving the append-only rule.
- **Verification result:** the focused repetition-3 suite passes 17 tests, and the complete MLIR suite passes 97 tests with one pre-existing IPython temp-directory warning. Q# telemetry also reports a harmless network failure at process exit in the sandbox.

## 2026-06-07 — Repetition-3 file consolidation

- **One repetition-3 module is the public implementation.** The unused `rep3_trivial_classbased.py` experiment was deleted. It implemented only an in-place X rewrite, was not imported anywhere, and did not satisfy the completed pass contract.
- **Callback registration lives with the pass.** The six-line `register_rep3_callbacks` helper was moved into `rep3_trivial.py`, and `rep3_trivial_callbacks.py` was deleted. Existing imports from `qstack_mlir.passes.rep3_trivial` are unchanged.

## 2026-06-13 — Current-qstack parity: canonical ISA and H2 pipelines

16. **Parity targets the current `src/qstack` behavior, not its legacy AST.** The MLIR implementation preserves observable compilation and execution workflows while retaining explicit SSA bits, static continuation menus, and explicit decoders. The old indentation parser, implicit measurement stack, and compiler-generated callback wrappers are not compatibility requirements.

17. **The canonical Clifford dialect now includes `Y`.** The original `cliffords_min` instruction set exposes `X`, `Y`, `Z`, `S`, `H`, `CX`, and `CZ`; the MLIR dialect and emulator now expose the same gate set. Repetition-3 remains scoped to its existing supported gate set and does not silently accept newly added canonical gates.

18. **H2 is a distinct parameterized dialect.** `h2.u1`, `h2.rz`, `h2.rzz`, and `h2.zz` thread qubits linearly. Numeric angles are f64 operation properties. Emulator cache keys include parameter values so operations at different angles cannot share an incorrect cached matrix.

19. **Clifford-to-H2 lowering follows the original decompositions and adds the missing `S` case.** `X` and `Y` lower to `U1`, `Z` and `S` lower to `RZ`, `H` lowers to `U1; RZ`, `CZ` lowers to `ZZ` plus two local `RZ` rotations, and `CX` lowers through target `H; CZ; H`. Unit tests compare every resulting matrix with the source Clifford up to global phase.

20. **Expanding ISA lowering uses an in-place recursive rewrite with explicit SSA threading.** This matches the existing Toy-to-Cliffords API while allowing one source operation to become an ordered H2 sequence. QEC transformations continue to use destination-building module-to-module rewrites because they widen function and kernel boundaries.

21. **The QSTACKQASM frontend recognizes direct H2 operations.** `qstack/h2.inc` declares the H2 gate set, and lowering handles parameterized one- and two-qubit gates. This is an interim built-in dispatch mechanism; dialect-driven include resolution remains future extensibility work.

22. **H2 pipeline parity is executable.** Tests cover direct H2 surface lowering, Toy-to-Cliffords-to-H2 Bell execution, repetition-3 followed by H2 execution, and repetition-3 applied twice followed by H2 execution. The complete MLIR suite passes 107 tests. The existing IPython temporary-directory warning and Q# telemetry network failure remain harmless sandbox/environment messages.

23. **Gate parameters accept signed numeric literals.** H2 decompositions require negative angles such as `-pi/2`; the surface grammar now accepts an optional sign specifically on gate parameters. Register sizes, indices, and switch labels remain unsigned.

## 2026-06-14 — ISA pass dispatch consistency

24. **Cliffords-to-H2 now uses the shared handler-registry pattern.** `CliffordsToH2Compiler` subclasses `BaseOpRewriter` and maps each canonical Clifford operation type to a dedicated handler, matching `ToyToCliffordsCompiler`. Multi-operation expansion remains handler-local: handlers build an ordered H2 sequence, replace the source SSA results with the sequence outputs, and erase the source op.

25. **Local ISA rewriters skip function declarations.** `BaseOpRewriter` now walks only `func.func` definitions. Body-less selector and decoder declarations are symbol interfaces and contain no operations to rewrite.

## 2026-06-14 — Steane [[7,1,3]] parity

26. **Steane is a seven-wide destination-building QEC rewrite.** Every logical qubit SSA value expands to seven physical values across function signatures, calls, kernels, selectors, and invokes. Existing selector and decoder declarations remain unchanged, following the same callback-boundary rule as repetition-3.

27. **Allocated logical qubits are prepared as encoded `|0>`.** The pass emits the legacy Steane preparation circuit (`H` on lanes 4, 5, and 6 followed by nine `CX` gates) before rewriting the source operations on each newly allocated seven-qubit block.

28. **The supported logical gate set matches the current legacy Steane compiler.** `X`, `Z`, and `H` lower transversally, and `CX` lowers pairwise across two blocks. Other canonical Cliffords fail with `SteaneCompileError` instead of surviving as incorrectly unencoded operations.

29. **Syndrome extraction is explicit quantum IR.** Each correction round allocates three ancillas in a nested `qstack.kernel`, extracts the three stabilizer bits, and threads the seven data qubits back. Bit-error and phase-error rounds use the same Hamming syndrome table and route through static correction menus containing identity plus one correction function per physical lane.

30. **Steane corrects after preparation and after every logical gate.** This is deliberately more regular than the legacy scheduler, which inserts initial rounds and then rounds between non-final instructions. The regular schedule simplifies SSA ownership and ensures the final logical gate is also followed by correction.

31. **Final logical measurement uses an explicit decoder.** Seven physical measurements leave the outer allocation kernel and feed `qstack.decode @steane_decode` at function scope. The decoder corrects one classical bit fault using the Steane syndrome and returns logical parity. `register_steane_callbacks` installs both this decoder and the three-bit syndrome selector.

32. **Generated allocating kernels establish that nested allocation is useful IR.** Steane requires three temporary syndrome ancillas while seven encoded data qubits remain live. Source modules containing their own nested bit-producing kernels are still rejected by the pass; general source-kernel restructuring remains separate work.

33. **Active correction currently selects inside the enclosing kernel.** The nested syndrome kernel returns its bits to the surrounding allocation body, where `qstack.select` and `qstack.invoke` choose and apply a correction continuation. The emulator and current verifier support this shape, but `DESIGN.md` describes selectors as function-scope operations. Lifting each correction boundary to function scope will require kernel splitting and is retained as design-alignment debt.

34. **Steane support symbols are reserved and the pass is not yet self-composable.** The pass adds `@steane_decode`, `@steane_syndrome`, identity, and fourteen correction helpers. A source collision is rejected rather than shadowed. Applying Steane a second time currently encounters those reserved symbols and is intentionally unsupported.

35. **Steane verification covers structure, behavior, and composition.** Tests exercise encoded logical zero and one, logical Bell correlation, all seven single-bit decoder faults, all syndrome labels, recursive selector preservation, explicit unsupported-gate rejection, and Steane-to-H2 execution. The complete MLIR suite passes 117 tests. `mlir/examples/6.steane.ipynb` provides the notebook counterpart.

## 2026-06-14 — QEC operation dispatch consistency

36. **Steane operation rewriting is handler-driven.** The function rewriter now maps every supported source operation type, including terminators and qstack control operations, to a dedicated handler. Unsupported operations use one centralized error path. The module-level pass remains custom because it widens symbols and coordinates generated support functions; only local operation dispatch adopts the registry pattern.

37. **Handler-registry completeness is tested.** The Steane suite asserts the exact supported operation-type set, and the complete MLIR suite passes 118 tests after the dispatch refactor.

## 2026-06-14 — Runtime observability parity

38. **The MLIR emulator uses the existing `qstack` logger for execution tracing.** At `DEBUG`, it reports simulator restarts, gate evaluation with physical wire indices, measurement outcomes, selector inputs and choices, and decoder inputs and results. Logging remains silent by default and follows Python's built-in logging configuration, matching the original notebook workflow.

39. **Steane callbacks log syndrome and decoding decisions.** The syndrome selector reports the measured syndrome and selected correction lane; the decoder reports the seven physical outcomes, computed syndrome, and corrected lane. This restores the original example's ability to expose both quantum evaluation and classical QEC decisions.

40. **The Steane notebook shows the compiler transformation and a traced evaluation.** It prints each compiled MLIR module, enables `qstack` debug logging for one encoded Bell shot, then restores `INFO` before collecting histogram shots. The compiled IR is intentionally verbose: making allocation widening, transversal gates, syndrome kernels, static continuation menus, and decoding visible is part of the example's purpose.

## 2026-06-14 — Notebook parity follow-up

41. **The numbered notebook set targets examples 0 through 6; Qiskit is out of scope.** The Qiskit comparison notebook is intentionally not being ported to the MLIR implementation. Notebook parity means preserving each qstack example's teaching purpose with the MLIR architecture, not reproducing unrelated framework integrations.

42. **The Bell notebook again starts at the Toy abstraction layer.** Now that the Toy dialect and emulator semantics exist, `0.bell.ipynb` uses `mix` and `entangle`, prints the lowered IR, shows one concrete shot, and then plots the Bell histogram. The previous claim that Toy was unported was stale.

43. **Repeat-until-success demonstrates both evaluator control and compilation.** `3.repeat_until_success.ipynb` implements a Toy `repeat_until_zero` protocol with a static continuation menu and host selector, enables `qstack` debug logging for one execution, then compiles the complete recursive program to Cliffords and displays the transformed IR. Unlike the legacy callback model, evaluator callbacks do not return new quantum kernels; retry bodies are statically represented and compiler-visible.

44. **The compilation notebook covers the implemented stack end to end.** `5.compile.ipynb` now prints and executes Toy, Clifford, H2, Rep3, Rep3-to-H2, and concatenated Rep3 modules, prints the Steane module, and traces one encoded execution. Independent branches clone the Clifford module because local ISA passes mutate in place while QEC passes return destination-built modules.

## 2026-06-21 — Phase E ISA decoupling and atoms

45. **Surface gate names now live only in include files.** The `.inc` files declare public QSTACKQASM gate names, parameter names, and qubit arity. Dialect files no longer need duplicate surface-name metadata.

46. **The include-to-IR convention is `<isa>.<gate>`.** An include with `#pragma qstack.isa atoms; gate rz(theta) q;` resolves the surface call `rz(...)` to the IR op `atoms.rz`. The same surface spelling under `h2.inc` resolves to `h2.rz`.

47. **Include declarations are validated against IRDLOps.** Lowering validates that every declared include gate has a matching op, matching property names, and matching linear qubit operand/result arity before emitting compute ops.

48. **Compute semantics live on op classes via `unitary()`.** `ModuleEvaluator` handles qstack core/control-flow ops directly, but executable compute gates are dispatched structurally through their dialect op's `unitary()` method. Parameterized ops read their own IRDL properties when building runtime matrices.

49. **QSTACKQASM v1 supports multiple ISA includes with disjoint gate names.** Includes are merged into one surface gate table so programs can combine a base ISA with extension dialects. If two includes declare the same surface gate name, lowering rejects the program until a qualified-call syntax exists.

50. **Atoms v1 is gate-level only.** The neutral-atom ISA exposes `atoms.rz`, `atoms.sx`, and `atoms.cz`, with `cliffords2atoms` lowering verified by matrix tests. Geometry, movement, blockade constraints, loss/leakage, scheduling, and other hardware-rich atom concerns are intentionally deferred.

51. **Unitary matrix definitions are dialect-local.** The shared evaluator contract is only the `UnitaryGateOp` protocol. Each ISA dialect owns its own matrix constants and parameterized matrix factories, so semantics do not accumulate in a central gate table.

52. **`UnitaryGateOp` lives with the core dialect contract.** The protocol is defined in `dialect/core.py` rather than a separate semantics module because it is the structural contract compute dialect ops implement for qstack evaluator execution.

53. **User `def` symbols shadow included ISA gates.** Surface lowering resolves a call against hoisted user definitions before consulting the merged include gate table. Includes provide the ambient gate vocabulary, but local program symbols take precedence when names collide.

54. **ISA op lookup lives under the dialect package.** The dialect registry is `qstack_mlir.dialect.registry`; include resolution validates declarations through that registry and stores the resolved IRDL op type on each `GateDecl`. Lowering consumes the resolved declaration instead of consulting the registry directly.

55. **`Machine` is the hybrid quantum machine.** `Machine` is composed of explicit `qpu` and `cpu` processors so qstack programs can mix quantum state evolution with classical callback-driven control. `QPU` owns quantum state; qubit allocation, unitary application, measurement, reset, and quantum noise are QPU responsibilities because they mutate or observe that state. `CPU` owns classical state; `qstack.select` and `qstack.decode` evaluation are CPU responsibilities because they consume classical data through host callbacks. `ModuleEvaluator` is the IR walker that coordinates SSA/control-flow and delegates processor-specific work.

56. **`Machine.eval` is the repeated-execution API.** The temporary `Machine.shots` convenience method was removed to stay closer to the original qstack `Machine` shape. `Machine.single_shot` runs one function invocation, and `Machine.eval(..., shots=N)` returns `Results`; `Results.shots` remains only the count property.

57. **The MLIR walking execution layer is `ModuleEvaluator`.** The evaluator is separate from `Machine` because walking MLIR is reusable infrastructure for execution and future compiler-pass validation. `Machine` remains the public hybrid quantum machine; `ModuleEvaluator` evaluates a module against the machine's QPU/CPU processors.
