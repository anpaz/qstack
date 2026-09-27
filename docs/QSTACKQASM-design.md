# OpenQASM 3.0 as the qstack Surface Language — Design Specification

**Status:** Draft v1
**Date:** 2026-05-22
**Companion:** [DESIGN.md](DESIGN.md) (qstack MLIR IR)

---

## 1. What this document is

qstack's surface language, QSTACKQASM, is inspired by OpenQASM 3.0, restricted to the subset that maps cleanly onto qstack's IR, plus one small addition. A reader familiar with OpenQASM 3.0 will recognize its keywords, grammar, and gate-call syntax unmodified. What changes is which programs qstack accepts, and, in a few places, what a construct actually does once compiled.

The guiding principle was to restrict OpenQASM, not extend it. qstack's IR was designed first (see [DESIGN.md](DESIGN.md)); this document describes the largest fragment of OpenQASM 3.0 that fits that IR without bending it. The one exception is `extern selector`, a single new modifier on the existing `extern` declaration, introduced for a callback role OpenQASM has no syntax for: choosing which of several compiled continuations to run next, rather than computing a value (§3.4).

Because this is a restriction rather than an extension, some valid OpenQASM programs have no equivalent here. Programs relying on mutable classical state, loops with a runtime-determined bound, or pulse-level timing cannot be expressed in this language. This is not an oversight: none of those constructs survive translation to an IR that is purely quantum, treats classical logic as an opaque callback boundary, and compiles ahead of time against a closed set of continuations. §6 lists the specific rejections and traces each to the constraint behind it.

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

Every keyword in this file is OpenQASM 3.0 except `extern selector`, which is a one-word modifier on standard `extern`.

---

## 3. Declaration Forms

### 3.1 `gate` — pure unitary subroutines

A `gate` declaration is identical to OpenQASM 3.0: its body is purely unitary, with no `measure`, no `qreg`, no `bit`, no `creg`, and no `extern` calls, and it has no return value. Its signature is a parameter list followed by a list of qubit arguments, exactly as in OpenQASM.

### 3.2 `def` — allocating subroutines

A `def` declaration is identical to OpenQASM 3.0, with one added constraint (§4.1): a `def` body may declare local `bit`s, contain `measure`, and contain at most one inner `qreg`. It may optionally return a `bit` or a fixed-size `bit[k]` (`def foo(qubit q) -> bit { ... }`, `def syndrome(qubit q) -> bit[3] { ... }`).

Every qubit parameter is also returned, unconditionally, in parameter order (§4.6). This is separate from the `-> bit`/`-> bit[k]` return, which is the only channel bits use to leave a `def`. There is no inference of which parameters "survive" a body — a parameter that gets measured inside is still returned; §4.7 describes what it is bound to when it comes back.

### 3.3 `extern` — host-language decoders

An `extern` declaration is identical to OpenQASM 3.0: it declares a body-less classical function, implemented separately in host-language code and registered by symbol name.

```qasm
extern majority_vote(bit, bit, bit) -> bit;
```

### 3.4 `extern selector` — host-language continuation choosers (the one extension)

The single syntactic extension over OpenQASM 3.0. Declares a body-less host-language callback whose return value is a continuation label (an integer) rather than a classical data value:

```qasm
extern selector apply_corrections(bit, bit) -> int;
```

The integer it returns selects which case of a downstream `switch` runs next (§3.6).

The `selector` modifier is the only way the surface language distinguishes selectors from decoders. Both are declared with `extern`; the modifier signals the call-site shape — a `switch` consumes a selector's result, treating each `case` as a continuation, while a plain `extern`'s result is a `bit`, consumed like any other.

### 3.5 Top-level program body

A file may have at most one top-level `qreg` declaration (§4.1). The top-level body is the program's entry point: the top-level `creg` receives its measured bits, and the program's result is the final content of that `creg`.

The entry point has no qubit parameters, so it has nothing to return them to — every `qreg` element it uses must instead be measured (directly, or after being threaded through one or more calls) before the program ends. This is the same consumption rule §4.8 states for any body; the entry point gets no exemption and no automatic cleanup measurement. A `qreg` element left live at the end of the top-level body is a compile error, not a silently inserted `measure`.

### 3.6 `if/else`, `switch/case`, `for`, `while` — control flow

**`if (cond) { ... } else { ... }`** — `cond` must be a comparison of a single `bit` to a literal (`m == 0`, `m == 1`).

**`switch (selector_call(b1, ...)) { case 0: ... case k: ... }`** — `selector_call` must be either a built-in comparison, as used by `if`, or an `extern selector` symbol. Each `case` arm is a closed alternative; a `default:` arm is permitted and is chosen when the selector returns any unlisted integer.

**`for i in [a:b]` / `for i in [a:b:c]` / `for i in {literal, literal, ...}`** — bounds must be compile-time constants. The loop is unrolled at compile time into one copy of the body per iteration, with `i` substituted; it is not a runtime construct.

**`while (cond) { body }`** — `cond` must be a single `bit` or an `extern selector` call result. This desugars to a recursive `def`: the body runs once, then a selector chooses between stopping and recursing. All bits and qubits referenced inside the body are threaded through the recursive call automatically.

Every branch of an `if`/`else` or `switch`/`case` must use and produce the same set of qubits. A construct where one branch touches a qubit another branch does not is a compile error — branches are required to agree on their qubit footprint, so that control flow has one unambiguous effect on the surrounding scope regardless of which branch runs.

### 3.7 `include` and instruction-set selection

Each qstack instruction set ships an include file at a conventional path, `qstack/<isa>.inc`:

```qasm
include "qstack/cliffords.inc";
```

The include file declares every gate the instruction set exposes, with its parameter list and qubit arity, and may also declare standard decoders the instruction set provides. A file may include multiple instruction-set files when their gate names are disjoint, allowing a base instruction set to compose with extensions such as magic-state mechanisms. Including two files that declare the same gate name is a compile error until a qualified-call syntax exists.

A common auxiliary include, `qstack/aux.inc`, provides `reset` and `barrier`. An instruction set that wants to offer these operations includes or re-exports `aux`; using `reset` or `barrier` without it is a compile error.

### 3.8 Gate modifiers

Modifiers write a gate call as a transformation of another gate: `inv @ U` (inverse), `pow(k) @ U` (repetition or fractional power), and `ctrl @ U` / `ctrl(n) @ U` / `negctrl @ U` (controlled and negative-controlled forms).

- `inv @ U` is the inverse of `U` — for example, `inv @ s` is `sdg`. Self-inverse gates collapse to `U` itself.
- `pow(k) @ U` for a positive integer `k` is `U` repeated `k` times; `pow(0)` is the identity, equivalent to omitting the gate; `pow(-k)` is `pow(k) @ inv @ U`. A non-integer `k` is accepted only when the active instruction set provides a continuous-rotation form of `U`.
- `ctrl @ U`, `ctrl(n) @ U`, and `negctrl @ U` require the active instruction set to define a controlled form of `U` — for example, `ctrl @ x` is `cx`. If it does not, this is a compile error naming the missing instruction-set-and-gate combination. Synthesizing an arbitrary controlled gate from first principles is not supported.

---

## 4. Structural Constraints

These constraints are the price of fitting OpenQASM 3.0 onto qstack's IR. Each is enforced at compile time with an explicit error naming the offending construct.

### 4.1 One allocation per body

Each `def` body, and the top-level program body, may contain at most one `qreg` declaration; a `gate` body may contain none. This keeps each `def`'s resource footprint visible from its declaration alone. To compose multiple allocations, factor each into its own `def`.

### 4.2 Bits are single-use

Every classical outcome in this language has exactly one consumer. Classical bits are physically copyable, so nothing about a *source-level* read of a bit twice needs to be forbidden on its own terms (§4.2.1) — but the surface currently forbids it anyway, because there is no way yet to express a second, independent read of the same value. Concretely, every `bit` slot in a `def` body, in the top-level body, and in `creg` indices is written exactly once and read exactly once:

- `bit m; measure q -> m;` writes `m`.
- A subsequent `if (m == k)`, `switch (selector(m, ...))`, `extern(m, ...)`, or `bit b = extern(m);` reads `m`, consuming it.
- Writing `m` twice is an error. Reading `m` twice is an error. Writing without ever reading is an error.

#### 4.2.1 Why — and the cost

Classical bits are physically copyable, so this restriction is not a physical necessity, the way no-cloning is for qubits, and it is not fundamental to the surface language either. The property it protects — that every classical value has exactly one consumer — is real and worth keeping: it is what lets qstack's compiler passes be checked by comparing small, local replacements rather than whole programs. But that property only needs to hold in the compiled result, not in the source text a person writes.

The cost is real and falls on one common QASM 3.0 idiom: a single bit referenced from multiple `if`/`switch`/`extern` sites is not allowed. For example:

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

// (ii) Use a switch when there is more than one bit-pattern to dispatch on:
bit m;
measure q -> m;
switch (m) {
  case 1: { x q; z r; }
  case 0: { }
}

// (iii) Factor through an extern selector when the decisions are genuinely
// independent and the selector's logic justifies a host-language callback:
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

Rewrites (i) and (ii) are mechanical. (iii) is appropriate when the dispatch is complex enough to warrant explicit host-language code. The author of a qstack program is expected to make this choice consciously — the surface language does not silently fan a bit out behind the scenes.

There is currently no mechanism to duplicate a bit and keep the compiled result single-use. If a future version of the surface language relaxes this and admits implicit fan-out, closing that gap will require adding one (see §7 item 5).

### 4.3 Qubits are threaded automatically

Qubits are written in OpenQASM 3.0 style — the same `q[i]` referenced across many gates — and the compiler follows each qubit's identity through the program automatically. No restriction applies beyond what OpenQASM 3.0 already imposes: a qubit must be in scope to be referenced, and a gate cannot be applied to a name whose current value was just measured away. Reading a name again after a `measure`, rather than gating on it, is fine — §4.7 describes what the name is bound to at that point.

A qubit operated on inside a `def`'s body originates either as a parameter of the `def` or as an element of the body's single `qreg`. Mixing the two is fine; referencing an outer-scope qubit that was not passed as a parameter is an error.

### 4.4 Bits cross `def` boundaries only via the declared return type

A `def` with no return type cannot leak a bit to its caller; any bit measured inside must be consumed inside. A `def` may declare `-> bit` (return exactly one bit) or `-> bit[k]` for a compile-time-constant `k ≥ 1` (return exactly `k` bits). Both forms are standard OpenQASM 3.0.

### 4.5 Recursion and mutual recursion

Allowed via standard symbol-table resolution. Mutual recursion requires a forward declaration — a body-less `def name(...);` ahead of the cycle. Unbounded recursion at runtime is a compile error: a recursive `def` must offer at least one non-recursive path out of every reachable call, since the set of continuations a program can reach is fixed at compile time.

### 4.6 Every qubit parameter is returned

A `def`'s signature is exactly its declared qubit parameters, in order, both in and out. Calling a `def` with `N` qubit arguments always yields `N` qubits back, in the same order, regardless of what the body did to any of them. There is no analysis of which parameters "survive" a body — a parameter is never silently dropped from the return list because it happened to be measured.

This makes a call opaque: a caller reads a `def`'s effect on its qubit arguments entirely from its declared arity, never from its body. Recursive and mutually recursive `def`s benefit particularly — a forward declaration's signature is final the moment its parameter list is written, with no need to inspect, or even to have yet written, the body to know what comes back.

The corollary: every qubit a call returns is live and must be consumed — measured, or passed on to another call, or returned onward — before the enclosing scope exits (§4.8). This holds even when the returned qubit is, physically, a freshly prepared `|0⟩` that the callee substituted in because the corresponding parameter was measured internally (§4.7): the caller has no way to tell, and is not given one, so it must measure that qubit like any other live result.

### 4.7 Measurement is Z-measurement plus reset

`measure q -> c;` measures `q` in the computational basis, and that measurement consumes `q`'s current value — the name can no longer be read as if it still held the pre-measurement state. This matches real OpenQASM's outcome, but not its resource model: OpenQASM treats qubits as durable locations that survive a `measure`, while qstack's qubits are consumed by use.

For a local ancilla, an element of the body's `qreg`, that is the end of the story: once measured, the name is retired.

For a `def`'s qubit parameter, it cannot be the end of the story, because §4.6 requires every parameter to be returned. So measuring a parameter implicitly prepares one fresh `|0⟩` qubit and rebinds the parameter's name to it, transparently, at the point of measurement. There is no surface syntax for this — no new keyword, no visible `reset`; the name is simply usable again after the `measure` statement, now holding a freshly prepared `|0⟩`:

```qasm
def teleport(qubit source, qubit target) {
  qreg shared[1];
  bit m0;
  bit m1;

  h shared[0];
  cx shared[0], target;
  cx source, shared[0];
  h source;
  measure source -> m0;      // source's pre-measurement value is consumed here;
                              // "source" now names a fresh, compiler-provided |0>.
  measure shared[0] -> m1;   // shared[0] is a local ancilla: retired, not replaced.

  switch (teleport_fix(m0, m1)) {
    case 0: { }
    case 1: { x target; }
    case 2: { z target; }
    case 3: { x target; z target; }
  }
  // teleport returns (source, target) — both are live and both must be
  // consumed by the caller, exactly like any other pair of returned qubits.
}
```

Calling this `def` with two qubits returns two qubits. The one that lines up with `source` is a plain `|0⟩`, no different from any other returned qubit — and, per §4.6, the caller must measure it, or pass it on, like any other live result. There is no surface syntax to mark a returned qubit as already known to be `|0⟩` and skip the measurement: §4.6's opacity means every returned qubit receives the same treatment.

### 4.8 Resource consumption is enforced, not inferred

Every qubit and bit that comes into existence in a body — a borrowed parameter, a `qreg` allocation, a `measure` result — must be consumed by something before the body ends: a gate, another `measure`, a `decode`/`switch`/`if`, a call, or the value being returned. This is the same underlying property as §4.2's bit rule, applied uniformly to qubits: every value has exactly one consumer, and the compiler names the specific resource that violates this, rather than silently discarding it.

Concretely:

- A local ancilla that is touched at all must be measured before the body ends; leaving one live is an error.
- A bit that is written (by `measure`) must be read exactly once (§4.2); a bit that is never read is an error.
- A qubit returned by a call and not otherwise used must still be measured or returned onward (§4.6); dropping it silently is an error, not a warning.

The one thing this rule does not require: a `qreg` or `bit` that is declared and never referenced at all needs no disposition, since nothing was ever allocated for it. Declaring `qreg spare[1];` and never touching `spare[0]` is legal. The moment `spare[0]` appears in a gate, `measure`, or call, it becomes live and the rules above apply to it.

---

## 5. Accepted OpenQASM 3.0 Features (Summary)

- `OPENQASM 3.0;` header
- `include`
- Comments (`//`, `/* */`)
- Annotations `@name.path` — preserved as metadata on the compiled program; not yet given meaning by any compiler pass
- `qreg q[n];` / `qubit[n] q;` / `qubit q;` (synonyms)
- `creg c[n];` / `bit[n] c;` / `bit b;` (synonyms)
- `gate` declarations and calls
- `def` declarations and calls
- `extern` declarations and calls
- `extern selector` declarations and calls (one-modifier extension)
- `measure q -> c;` and `c = measure q;` (§4.7: measuring a `def` parameter is Z-measurement plus an implicit reset to a fresh `|0⟩` — a semantic, not syntactic, difference from OpenQASM)
- `if/else { ... }` (block form)
- `switch/case/default`
- `for i in [a:b]` / `[a:b:c]` / `{lits}` (compile-time bounds)
- `while (bit_cond)` (sugar over recursive `def`)
- Gate modifiers: `inv @`, `pow(k) @`, `ctrl @`, `negctrl @`, `ctrl(n) @` (§3.8)
- `const` (for compile-time-constant gate-parameter literals only)
- Numeric literals as static gate parameters: `pi`, `pi/2`, `0.5`, etc.
- Recursion and forward declarations

---

## 6. Rejected OpenQASM 3.0 Features

Each rejection traces to a specific property of qstack's IR. The compiler reports an error pointing at the offending construct.

### 6.1 Closed-menu / ahead-of-time compilation conflicts

| Rejected                           | Why                                                                                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `while (cond)` with non-bit `cond` | Runtime-bounded loops over mutable classical state cannot fit a set of continuations fixed at compile time. The bit-conditioned form is supported as §3.6 sugar. |
| `end;` (early-terminate program)   | Would drop live qubits and bits without consuming them.                                                                              |
| `break` / `continue`               | Interact with bit and qubit single-use rules inside loop bodies in ways that cannot be checked locally; no clean rewrite exists yet. |

### 6.2 Global classical state conflicts

| Rejected                                                                                 | Why                                                                                                                                                 |
| ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mutable classical variables (`int x; x = x + 1;`)                                        | qstack has no mutable classical state; classical computation lives in `extern`.                                                                     |
| Non-bit classical program variables (`int`, `uint`, `float`, `angle`, `bool`, `complex`) | Same. Only `bit` exists at program scope. Numeric literals as static gate parameters are fine — they are compile-time constants, not runtime values. |
| Classical expressions in `if`/`switch` beyond the built-in forms                         | Only `if (m == k)` and `switch (extern_selector(...))` are recognized. Anything richer must go through an `extern selector`.                        |
| `input` / `output` classical modifiers                                                   | Classical inputs and outputs flow through `extern` callbacks and the top-level `creg`, not a separate parameterization layer.                        |

### 6.3 Features with no analogue in this model

| Rejected                                          | Why                                                                          |
| -------------------------------------------------- | ----------------------------------------------------------------------------- |
| `duration`, `stretch`, `delay`, `box`, all timing | This model has no timing layer; noise and timing are handled at the emulator level. |
| `defcal`, `cal { }`, all OpenPulse                | This model has no pulse layer; instruction sets are gate-level.              |
| `gphase`                                          | Global phase is unobservable in this model and is not represented.           |

### 6.4 Single-use conflicts

| Rejected                                                          | Why                                                                                                                                  |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `let q2 = q[0:3];` (qubit register aliasing/slicing)              | Creates two names for the same qubit, which contradicts single-use qubit semantics.                                                  |
| Reusing a qubit name after `reset` as if freshly allocated        | To get a fresh qubit, enter a new `def` with a `qreg`. `reset` is just a gate.                                                       |
| Reading the same `bit` from multiple `if`/`switch`/`extern` sites | Bits are single-use. Combine into one `if`/`switch`, or factor through an `extern selector`. See §4.2.1 for worked rewrites.        |
| Treating a measured qubit's name as unaffected, expecting it to still read the pre-measurement state | `measure` consumes the current value. The name is either retired (a local ancilla) or rebound to a fresh `|0⟩` (a `def` parameter, §4.7). This differs from the row above: that row is about a person writing `reset` and expecting a name to count as freshly allocated; this is the compiler substituting the replacement itself, and only for parameters, which must be returned regardless. |

---

## 7. Open Items for v2

These were deliberately scoped out of v1 to keep the surface tight. Each is a small, principled extension if user demand materializes.

1. Generic gate synthesis to back `ctrl @ U` for instruction sets that do not declare the rule (§3.8).
2. `break` / `continue`, with a worked-out single-use story for loop bodies.
3. `let` slicing as a compile-time renaming, with no runtime aliasing, for ergonomic register chunking.
4. Annotations with semantic effect — compiler behavior that recognizes `@qstack.noise(...)` or similar.
5. Implicit bit fan-out — relax §4.2 to allow a single `bit` to be read from multiple sites, with the compiler inserting the duplication needed to keep the compiled result single-use. Gains back the natural QASM 3.0 idiom shown in §4.2.1. Worth revisiting if those rewrites prove a recurring source of friction in real programs.
