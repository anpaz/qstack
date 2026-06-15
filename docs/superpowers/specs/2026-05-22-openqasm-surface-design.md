# OpenQASM 3.0 as the qstack Surface Language — Design Specification

**Status:** Draft v1
**Date:** 2026-05-22
**Companion:** [mlir/DESIGN.md](../../../mlir/DESIGN.md) (qstack MLIR IR)

---

## 1. Goal and Philosophy

This spec defines a **strict-but-not-extended subset of OpenQASM 3.0** as the surface language for qstack. The principle is:

> Take OpenQASM 3.0 and strip it down to the fragment that maps cleanly to the qstack MLIR IR. Add the smallest possible number of new constructs — exactly one — for things the IR genuinely needs that OpenQASM 3.0 cannot express.

The result is a file that looks like ordinary OpenQASM 3.0 to a reader, accepts most of OpenQASM 3.0's gate-and-control surface unmodified, and rejects features that conflict with qstack's IR thesis (purely quantum IR, opaque host-language callbacks, closed-universe AOT compilation, linear single-use qubits and bits).

**The one syntactic extension:** an additional modifier on `extern` — `extern selector` — declaring a host-language callback whose role is to choose a continuation label rather than compute a classical value. Everything else is stock OpenQASM 3.0.

**Non-goals.** This is not an attempt to make qstack adapt to OpenQASM. It is the opposite: take OpenQASM and restrict it. Programs that need OpenQASM features qstack rejects (mutable classical state, runtime-bounded loops, pulse-level calibration, timing) cannot be written in this language and must be expressed in a different tool.

---

## 2. An Example

The headline `prepare_one` program from the IR spec, written in this surface language:

```qasm
OPENQASM 3.0;
include "qstack/cliffords.inc";

// Host-language selector: returns 1 to retry, 0 to exit.
extern selector repeat_until_one(bit) -> int;

// Allocating subroutine. One internal qreg, one internal bit.
def prepare_one(qubit q) {
  qreg ancilla[1];
  bit m;
  h q;
  cx q, ancilla[0];
  measure ancilla[0] -> m;
  switch (repeat_until_one(m)) {
    case 0: { }                   // done
    case 1: { prepare_one q; }    // retry
  }
}

// Top-level: one allocation, one surfaced bit.
qreg q[1];
creg c[1];
prepare_one q[0];
measure q[0] -> c[0];
```

Every keyword in this file is OpenQASM 3.0 except `extern selector`, which is a one-word modifier on standard `extern`. The lowering to qstack MLIR is mechanical (§5).

---

## 3. Declaration Forms

### 3.1 `gate` — pure unitary subroutines

Identical to OpenQASM 3.0. A `gate` body is purely unitary: no `measure`, no `qreg`, no `bit`, no `creg`, no `extern` calls, no return value. Its signature is `(params) qargs`.

Lowers to a `func.func` of MLIR type `(qubit×b) -> (qubit×b)` with **no enclosing `qstack.kernel`**.

### 3.2 `def` — allocating subroutines

Identical to OpenQASM 3.0, with one added constraint (§4.1). A `def` body may declare local `bit`s, contain `measure`, and contain at most one inner `qreg` (§4.1). It may optionally return a `bit` or a fixed-size `bit[k]` (`def foo(qubit q) -> bit { ... }`, `def syndrome(qubit q) -> bit[3] { ... }`).

Lowers to a `func.func` whose body wraps one `qstack.kernel`. The `qstack.kernel`'s allocations are the inner `qreg` (if any); its borrows are the `def`'s qubit parameters; its surfaced bits are consumed inside the body (by `switch`, `if`, `extern`, decoder calls, or recursive invocation) or — if the `def` declares a `-> bit` return — flow out as the function's result.

### 3.3 `extern` — host-language decoders

Identical to OpenQASM 3.0. Declares a body-less classical function:

```qasm
extern majority_vote(bit, bit, bit) -> bit;
```

Lowers to a body-less `func.func private` with the `qstack.decoder` attribute. The host-language implementation is registered separately by symbol name.

### 3.4 `extern selector` — host-language continuation choosers (the one extension)

The single syntactic extension over OpenQASM 3.0. Declares a body-less host-language callback whose return value is a continuation label (an integer) rather than a classical data value:

```qasm
extern selector apply_corrections(bit, bit) -> int;
```

Lowers to a body-less `func.func private` with the `qstack.selector` attribute. The integer it returns is the menu key for a downstream `switch` (§3.6).

The `selector` modifier is the only way the surface language distinguishes selectors from decoders. Both are `extern`; the modifier signals the call-site shape (`switch` consumes the result, treating each `case` as a continuation) versus value use (the result of a plain `extern` is a `bit` consumed normally).

### 3.5 Top-level program body

A file may have at most one top-level `qreg` declaration (§4.1). The top-level body is the implicit `@main` `func.func`: its `qstack.kernel` allocates the top-level `qreg`, the top-level `creg` receives the surfaced bits, and the function returns the bits of the `creg` as its result.

### 3.6 `if/else`, `switch/case`, `for`, `while` — control flow

All sugar over `qstack.select` with closed continuation menus.

**`if (cond) { ... } else { ... }`** — `cond` must be a comparison of a single `bit` to a literal (`m == 0`, `m == 1`). Lowers to a `qstack.select @__if_eq_N__(m)` with the built-in two-entry menu `{0: @else_block, 1: @then_block}` and auto-generated `func.func` symbols for each block body.

**`switch (selector_call(b1, ...)) { case 0: ... case k: ... }`** — `selector_call` must be either a built-in selector (`__if_eq_N__`) or an `extern selector` symbol. Each `case` arm becomes a `func.func` symbol; the set of `case` labels is the closed continuation menu. A `default:` arm is permitted and becomes the menu entry chosen when the selector returns any unlisted integer.

**`for i in [a:b]` / `for i in [a:b:c]` / `for i in {literal, literal, ...}`** — bounds must be compile-time constants. Unrolled at IR-construction time into `(b-a)/c` copies of the body with `i` substituted. Not a runtime construct.
**`while (cond) { body }`** — `cond` must be a single `bit` or `extern selector` call result. Lowers by introducing a fresh recursive `def __while_N__(...) { body; switch (...) { case 0: {} case 1: { __while_N__ ...; } } }` and replacing the `while` statement with a call to it. The closed menu is `{0: identity, 1: self-recursion}`. All bits and qubits referenced inside the body must be properly threaded through the recursive call by the lowering pass.

### 3.7 `include` and ISA selection

Each qstack ISA ships an include file under the conventional path `qstack/<isa>.inc`:

```qasm
include "qstack/cliffords.inc";
```

The include file contains:

1. A `#pragma qstack.isa <name>;` line that tells the parser which ISA dialect to resolve gate names against.
2. Body-less `gate` declarations for every op the ISA exposes (with their parameter lists and qubit arities).
3. Optionally, body-less `extern` declarations for ISA-provided standard decoders.

The user-facing surface is just `include`. The `#pragma` is the underlying mechanism and is not expected to appear in user-authored files. A file may include exactly one ISA `.inc`; multiple is a parse error.

A common auxiliary include — `include "qstack/aux.inc";` — brings in the `reset` and `barrier` ops from the `qstack_aux` dialect (§5.4). ISAs that wish to support these ops opt in by including or re-exporting `aux`.

---

## 4. Structural Constraints

These constraints are the price of fitting OpenQASM 3.0 onto qstack's IR. They are enforced at parse / lowering time with explicit error messages.

### 4.1 One allocation per body

Each `def` body, and the top-level program body, may contain **at most one `qreg` declaration**. A `gate` body may contain **none**. This makes the `def` ↔ `qstack.kernel` lowering one-to-one and keeps the kernel signature readable from the declaration.

To compose multiple allocations, factor each into its own `def`.

### 4.2 Bits are linear (single-use)

Every `bit` slot in a `def` body, in the top-level body, and in `creg` indices is **written exactly once and read exactly once**. Concretely:

- `bit m; measure q -> m;` writes `m`.
- A subsequent `if (m == k)`, `switch (selector(m, ...))`, `extern(m, ...)`, or `bit b = extern(m);` reads `m`, consuming it.
- Writing `m` twice is an error. Reading `m` twice is an error. Writing without ever reading is an error.

This rule is the parser-visible face of the IR's `!qstack.bit` linearity (§4.1 of DESIGN.md). It matches the post-refactor explicit linear typing and aligns with current qstack's de facto runtime stack-pop semantics (the pop _is_ the consume).

#### 4.2.1 Why — and the cost

Classical bits are physically copyable, so this restriction is _not_ a physical necessity (unlike no-cloning for qubits). It is a deliberate IR design choice: by making every classical fan-out impossible in the surface, we keep the use-def graph single-use everywhere, preserving the structural verifier checks, ZX/stabilizer canonical form, and statically checkable producer–consumer agreement enumerated in DESIGN.md §4.1.1.

The cost is real and falls on one common QASM 3.0 idiom: **a single bit referenced from multiple `if`/`switch`/`extern` sites is not allowed.** For example:

```qasm
// NOT ALLOWED — m is read twice.
bit m;
measure q -> m;
if (m == 1) { x q; }
if (m == 1) { z r; }
```

The rewrites for this pattern are:

```qasm
// (i) Combine into a single if when the two effects share a branch:
bit m;
measure q -> m;
if (m == 1) { x q; z r; }

// (ii) Use a switch when there is more than one bit‐pattern to dispatch on:
bit m;
measure q -> m;
switch (m) {
  case 1: { x q; z r; }
  case 0: { }
}

// (iii) Factor through an extern selector when the decisions are genuinely
// independent and the selector's logic justifies a host‐language callback:
extern selector decide_xz(bit) -> int;
bit m;
measure q -> m;
switch (decide_xz(m)) {
  case 0: { }
  case 1: { x q; }
  case 2: { z r; }
  case 3: { x q; z r; }
}
```

Rewrites (i) and (ii) are mechanical. (iii) is appropriate when the dispatch is complex enough to warrant explicit host‐language code. The author of a qstack program is expected to make this choice consciously — the surface language does not silently fan a bit out behind their back.

No `qstack.dup` op exists for bits in the IR; classical fan-out has no representation. If a v2 surface decides to relax this and admit implicit fan‐out, that decision will require adding a core op for it (see §8).

### 4.3 Qubits are threaded automatically

The user writes qubits in OpenQASM 3.0 style — referencing the same `q[i]` across many gates — and the parser threads SSA values through the lowered IR. No surface-visible restriction beyond what OpenQASM 3.0 already imposes (don't reference a qubit not in scope; don't operate on a measured qubit).

A qubit operated on inside a `def`'s body originates as either (a) a parameter of the `def` (borrow), or (b) an element of the body's single `qreg` (allocation). Mixing is fine; references to outer-scope qubits not passed as parameters are an error.

### 4.4 Bits cross `def` boundaries only via the declared return type

A `def` with no return type cannot leak a bit to its caller; any bit measured inside must be consumed inside. A `def` may declare `-> bit` (return exactly one bit) or `-> bit[k]` for a compile-time-constant `k ≥ 1` (return exactly `k` bits). Both forms are standard OpenQASM 3.0. The IR's kernel signature `(qubit × b) → (bit × a, qubit × b)` (DESIGN.md §4.2) supports this directly: a `def -> bit[k]` lowers to a `func.func` returning `k` bits plus the threaded borrows.

### 4.5 Recursion and mutual recursion

Allowed via standard symbol-table resolution. Mutual recursion requires forward declaration (a body-less `def name(...);` ahead of the cycle). Unbounded recursion at runtime (a recursive `def` with no `switch`/`if` selecting a base case) is a verifier error: the closed continuation menu must contain at least one non-self entry along every reachable path.

---

## 5. Lowering to qstack MLIR

Mechanical rules. The parser produces MLIR text directly; no intermediate AST is exposed to the user.

### 5.1 Declarations

| Surface                                    | MLIR                                                                                      |
| ------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `gate G(params) qargs { body }`            | `func.func @G(qubit×b) -> (qubit×b) { body }`                                             |
| `def F(qubit q, ...) { body }` (no `qreg`) | `func.func @F(qubit×b) -> (qubit×b) { body }`                                             |
| `def F(qubit q, ...) { qreg a[k]; body }`  | `func.func @F(qubit×b) -> (qubit×b) { qstack.kernel(...) { ^bb0(qubit×k): body } }`       |
| `def F(...) -> bit { qreg a[k]; body }`    | `func.func @F(qubit×b) -> (bit, qubit×b) { qstack.kernel(...) { ... ret bit, ... } }`     |
| `def F(...) -> bit[k] { qreg a[k]; body }` | `func.func @F(qubit×b) -> (bit×k, qubit×b) { qstack.kernel(...) { ... ret bit×k, ... } }` |
| `extern D(bit×k) -> bit;`                  | `func.func private @D(bit×k) -> bit attributes { qstack.decoder }`                        |
| `extern selector S(bit×k) -> int;`         | `func.func private @S(bit×k) attributes { qstack.selector }`                              |

### 5.2 Control flow

| Surface                                      | MLIR                                                                                |
| -------------------------------------------- | ----------------------------------------------------------------------------------- |
| `if (m == k) { A } else { B }`               | `qstack.select @__if_eq_k__(b = %m) continuations { 0 = @B_sym, 1 = @A_sym } : ...` |
| `switch (S(%b1, ...)) { case k: { K } ... }` | `qstack.select @S(...) continuations { k = @K_sym, ... } : ...`                     |
| `for i in [a:b] { body }`                    | `b-a` inlined copies of `body[i := constant]` at parse time                         |
| `while (m) { body }`                         | Recursive `def` desugar + `switch` (§3.6)                                           |
| `qreg q[k]; ... measure q[i] -> c[i];`       | One `qstack.kernel` with `k` allocations; each `measure` is `qstack.measure %qi`    |
| `bit b = D(m1, m2, ...);`                    | `%b = qstack.decode @D(%m1, %m2, ...) : ...`                                        |

Each auto-generated `_sym` is a fresh `func.func` whose signature is `(qubit × n) -> (qubit × n)` where `n` is the qubit footprint shared by every branch of the surrounding control construct. The lowering pass verifies that every branch uses and produces the same set of qubits — branches that diverge in qubit footprint are a parse error.

### 5.3 Gate modifiers

Modifiers (`inv @`, `pow(k) @`, `ctrl @`, `negctrl @`, `ctrl(n) @`) are surface syntax only. An early lowering pass expands them into a sequence of ops drawn entirely from the active ISA dialect, using per-ISA decomposition rules declared by the dialect:

- `inv @ U` → ISA-declared inverse op for `U` (e.g., `inv @ s → sdg`); identity for self-inverse `U` collapsed at lowering.
- `pow(k) @ U` for integer `k > 0` → `k` repeated `U`s; `pow(0)` → identity (drop); `pow(-k)` → `pow(k) @ inv @ U` recursively; non-integer `k` only when the ISA provides a continuous-rotation form.
- `ctrl @ U` / `ctrl(n) @ U` / `negctrl @ U` → ISA-declared controlled form (e.g., `ctrl @ x → cx`); otherwise a compile-time error.

No `qstack.ctrl` or `qstack.inv` ops exist in the IR — modifiers are gone after the expansion pass. The IR is purely ISA-level from that point forward.

If the active ISA does not declare a rule for a particular modifier×gate combination, the compiler fails at the modifier-expansion pass with a clear message (e.g., `"ISA 'cliffords' does not define 'ctrl @ rx'"`). Generic synthesis (decomposing arbitrary controlled gates from first principles) is not in v1.

### 5.4 `reset` and `barrier`

These are not part of the core qstack dialect (they are compute, in the sense that they act on qubits). They live in an auxiliary dialect `qstack_aux` declaring `qstack_aux.reset` and `qstack_aux.barrier`. ISAs that wish to support them depend on `qstack_aux` and re-export the ops in their `.inc` file. A `reset`/`barrier` in a file whose ISA does not opt in is a parse error.

---

## 6. Accepted OpenQASM 3.0 Features (Summary)

- `OPENQASM 3.0;` header
- `include`
- Comments (`//`, `/* */`)
- Annotations `@name.path` — preserved as opaque metadata on the lowered op, ignored by passes in v1
- `qreg q[n];` / `qubit[n] q;` / `qubit q;` (synonyms)
- `creg c[n];` / `bit[n] c;` / `bit b;` (synonyms)
- `gate` declarations and calls
- `def` declarations and calls
- `extern` declarations and calls
- `extern selector` declarations and calls _(one-modifier extension)_
- `measure q -> c;` and `c = measure q;`
- `if/else { ... }` (block form)
- `switch/case/default`
- `for i in [a:b]` / `[a:b:c]` / `{lits}` (compile-time bounds)
- `while (bit_cond)` (sugar over recursive `def`)
- Gate modifiers: `inv @`, `pow(k) @`, `ctrl @`, `negctrl @`, `ctrl(n) @`
- `const` (for compile-time-constant gate-parameter literals only)
- Numeric literals as static gate parameters: `pi`, `pi/2`, `0.5`, etc.
- Recursion and forward declarations

---

## 7. Rejected OpenQASM 3.0 Features

Each rejection traces to a specific qstack IR invariant. The parser produces an error pointing at the offending construct.

### 7.1 Closed-menu / AOT compilation conflicts

| Rejected                           | Why                                                                                                                                             |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `while (cond)` with non-bit `cond` | Runtime-bounded loops over mutable classical state can't fit the closed continuation menu. The bit-conditioned form is supported as §3.6 sugar. |
| `end;` (early-terminate program)   | Would drop linear qubits/bits on the floor; violates kernel allocation-scope invariants.                                                        |
| `break` / `continue`               | Interact with bit-and-qubit linearity inside loop bodies in ways that can't be checked locally; no clean desugaring.                            |

### 7.2 Global classical state conflicts (§4.5.3 of DESIGN.md)

| Rejected                                                                                 | Why                                                                                                                                                 |
| ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mutable classical variables (`int x; x = x + 1;`)                                        | qstack has no mutable classical state; classical computation lives in `extern`.                                                                     |
| Non-bit classical program variables (`int`, `uint`, `float`, `angle`, `bool`, `complex`) | Same. Only `bit` exists at program scope. Numeric literals as static gate parameters are fine — they're compile-time constants, not runtime values. |
| Classical expressions in `if`/`switch` beyond the built-in forms                         | Only `if (m == k)` and `switch (extern_selector(...))` are recognized. Anything richer must go through an `extern selector`.                        |
| `input` / `output` classical modifiers                                                   | Classical inputs/outputs flow through `extern` callbacks and the top-level `creg`, not a separate parameterization layer.                           |

### 7.3 No-IR-analogue features

| Rejected                                          | Why                                                                                           |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `duration`, `stretch`, `delay`, `box`, all timing | qstack IR has no timing layer; noise/timing live at the emulator level (§1.1.8 of DESIGN.md). |
| `defcal`, `cal { }`, all OpenPulse                | qstack IR has no pulse layer; ISAs are gate-level.                                            |
| `gphase`                                          | Global phase is unobservable in this model; not represented.                                  |

### 7.4 Linearity conflicts

| Rejected                                                          | Why                                                                                                                                  |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `let q2 = q[0:3];` (qubit register aliasing/slicing)              | Creates two names for the same qubit — contradicts `!qstack.qubit` linearity.                                                        |
| Reusing a qubit name after `reset` as if freshly allocated        | To get a fresh qubit, enter a new `def` with a `qreg`. `reset` is just a gate.                                                       |
| Reading the same `bit` from multiple `if`/`switch`/`extern` sites | `!qstack.bit` is single-use. Combine into one `if`/`switch`, or factor through an `extern selector`. See §4.2.1 for worked rewrites. |

---

## 8. Open Items for v2

These were deliberately scoped out of v1 to keep the surface tight. Each is a small, principled extension if user demand materializes.

1. **Generic gate synthesis** to back `ctrl @ U` for ISAs that don't declare the rule (§5.3).
2. **`break` / `continue`** with a worked-out linearity story.
3. **`let` slicing** as a parse-time renaming (no runtime aliasing) for ergonomic register chunking.
4. **Annotations with semantic effect** — passes that recognize `@qstack.noise(...)` or similar.
5. **Implicit bit fan-out** — relax §4.2 to allow a single `bit` to be read from multiple sites, with the parser auto-inserting a new core op `qstack.dup : !qstack.bit -> (!qstack.bit × n)` to keep the IR single-use. Costs one new core op and a small patch to DESIGN.md §4.3; gains back the natural QASM 3.0 idiom. Worth revisiting if the rewrites in §4.2.1 prove a recurring source of friction in real programs.

---

## 9. Relationship to the IR Refactor

This surface language is designed against the **post-refactor** qstack MLIR IR described in [mlir/DESIGN.md](../../../mlir/DESIGN.md). The parser produces MLIR module text consumable by the IR's verifier and lowering passes.

Programs written in this language can also be lowered against the **pre-refactor** Python-tree IR with one caveat: pre-refactor qubit references are non-linear, so the SSA threading the parser would do post-refactor is unnecessary. Bit linearity is already de facto enforced by the runtime measurement stack.

The surface language commits to no IR-implementation choices beyond what DESIGN.md already commits to.
