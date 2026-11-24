# QSTACKQASM — Design Specification

**Status:** Describes the implemented frontend (`src/qstack/surface/`)
**Date:** 2026-11-23
**Companion:** [DESIGN.md](DESIGN.md) (qstack IR)

---

## 1. What this document is

QSTACKQASM is qstack's surface language. It borrows OpenQASM 3's syntax, removes its classical computation, and lowers to the IR described in [DESIGN.md](DESIGN.md).

The IR was designed first, and QSTACKQASM keeps the part of OpenQASM 3 that fits it. It is not a subset of OpenQASM 3, and its programs are not meant for OpenQASM 3 toolchains. It differs in three ways:

- **One addition.** `extern selector` declares a host-language callback that chooses what runs next (§3.3). Apart from the header, it is the only new syntax.
- **One lifted restriction.** OpenQASM 3 declares all qubits globally. QSTACKQASM allows qubit declarations in any block, because a qstack kernel allocates its own qubits.
- **Some different meanings.** A measured qubit is reset rather than left in its measured state (§4.3), and a bit is read once (§4.2).

§6 lists the OpenQASM 3 features QSTACKQASM leaves out.

---

## 2. An example

```qasm
QSTACKQASM 0.1;
include "qstack/cliffords.inc";

// Host-language selector: 1 to retry, 0 when done.
extern selector repeat_until_one(bit) -> int;

def prepare_one(qubit q) {
  qubit a;
  bit m;
  h q;
  cx q, a;
  measure a -> m;
  switch (repeat_until_one(m)) {
    case 0 { }
    case 1 { prepare_one(q); }
  }
}

qubit q;
bit c;
prepare_one(q);
measure q -> c;
```

---

## 3. The language

A program is a header, then includes, then declarations (`extern`, `extern selector`, `def`), then the top-level statements.

### 3.1 Includes and gates

Each instruction set has an include file, such as `qstack/cliffords.inc`, that declares its gates with their parameters and qubit counts. A program can include several; two that declare the same gate name are an error. Gates come only from include files.

A gate is applied without parentheses around its qubits: `h q;`, `cx q, a[0];`, `skew(0.8) q;`. Gate parameters are numeric literals.

### 3.2 `extern`: decoders

`extern majority(bit, bit, bit) -> bit;` declares a decoder: a callback with no body, registered with the runtime by name. It takes bits and returns one bit. It is called with OpenQASM's syntax, and lowers to `qstack.decode`:

```qasm
bit b = majority(m0, m1, m2);
b = majority(m0, m1, m2);
```

### 3.3 `extern selector`: choosing what runs next

`extern selector fix(bit, bit) -> int;` declares a selector: a callback that takes bits and returns a case label. A selector used by a `switch` is declared `-> int`, and one used by a `while` is declared `-> bool`.

At runtime a selector returns its label as a string. `case 2` matches the label `"2"`. In a `while`, `"1"` runs the body again and `"0"` leaves the loop. A label that matches no case is a runtime error.

### 3.4 `def`

A `def` takes qubits and returns all of them, in order, whatever its body does. It is called with parentheses: `teleport(a[0], b);`. Calls are opaque: a caller sees only the declared qubits. `def`s can be recursive or mutually recursive, with no forward declarations.

### 3.5 Declarations

`qubit q;`, `qubit[3] a;`, `bit m;` and `bit[3] c;` can appear in any block. A register's elements are used one at a time, as `a[0]`.

### 3.6 `measure`

`measure a[0] -> c[0];`. See §4.3.

### 3.7 `switch`

`switch (fix(m0, m1)) { case 0 { } case 1 { x q; } }`. The expression is a selector call, and each label appears once.

### 3.8 `while`

`while (again(m)) { ... }`. The condition is a selector call. The body must measure every bit the condition reads, because each test uses its bits up.

### 3.9 `for`

`for int i in [0:2] { ... }`, `for int i in [0:2:4] { ... }` (start, step, stop) and `for int i in {0, 2} { ... }`. Ranges include both ends. Bounds are constants, and the loop variable can only index a register.

### 3.10 Top level

The top-level statements form `@main`. Any statement is allowed. The program returns the bits that are still unread when it ends.

---

## 4. Rules the grammar does not express

Each is enforced at compile time.

### 4.1 Qubits are measured by the block that declares them

A block measures every qubit it declares, if it uses it. A qubit that is declared and never used is never allocated.

A qubit that is live at a `switch` or `while` comes back live. An ancilla used only inside an arm or a loop body should therefore be declared there.

### 4.2 Bits are read once, in the kernel that measures them

A bit is read by a `switch`, a `while` or a decoder call, and each read uses it up. A bit that is never read is an error, except at the top level, where it is returned. `def`s do not take or return bits, and an arm or a loop body cannot read a bit measured outside it.

Bits can be copied physically, but single use gives every value in the IR exactly one consumer, which is what lets passes be checked by comparing dataflow graphs. Two decisions on the same bit have to be combined into one `switch`.

### 4.3 Measurement resets

`measure q -> c` consumes the value of `q`. If `q` is used again later in the same kernel, or the kernel must return it, the name is bound at once to a newly allocated `|0⟩`. Otherwise the name is retired.

In OpenQASM 3 the qubit instead keeps its measured state, so a program that measures a qubit and then uses it as a control means something different here.

---

## 5. Lowering

| QSTACKQASM | IR |
| --- | --- |
| `def` | A kernel that borrows its qubit parameters and returns them |
| Top level | `@main`, which returns the unread bits |
| Qubit declaration | One more allocation in the kernel, if the qubit is used |
| Gate, call | The operation, with each name rebound to its result |
| `measure` | `qstack.measure`, and one more allocation if the name is replaced |
| Decoder call | `qstack.decode` |
| `switch` | `qstack.select`, and one case kernel per arm, `@__qstack_case_<label>_<n>` |
| `while` | A loop kernel `@__qstack_while_<n>` and an exit kernel `@__qstack_while_<n>_exit` |
| `for` | Unrolled before lowering, one block per iteration |

Case, loop and exit kernels borrow every qubit live at the statement and return it. A `while` becomes a `select` with the loop kernel as case `"1"` and the exit kernel as case `"0"`. The loop kernel runs the body and ends in the same `select`, so each iteration is a recursive call. `<n>` counts arms or loops across the program, not iterations.

The lowering is not verified. The structural verifier checks its output, and every later pass is verified.

---

## 6. OpenQASM 3 features left out

| Left out | Why |
| --- | --- |
| Classical variables, types and expressions | Classical computation lives in callbacks. Only `bit` values exist, and gate parameters are literals. |
| `if`, `else` | Every choice is a `switch` on a selector. |
| `default` | A `select` lists its cases. An unlisted label is a runtime error. |
| Runtime loop bounds, `break`, `continue`, `end` | A program's kernels are fixed when it is compiled. `break`, `continue` and `end` would also leave qubits or bits unconsumed. |
| `bit` parameters and returned bits in `def` | Not implemented. The IR supports both. |
| `gate` declarations, gate modifiers | Not implemented. Gates come from include files. |
| `reset` | Measuring a qubit that is used again already resets it. |
| Register aliasing (`let`), whole-register operands and register parameters | Not implemented. Aliasing would also give one qubit two names. |
| `c = measure q;`, `qreg`, `creg` | One form of each is supported: `measure q -> c;`, `qubit`, `bit`. |
| Timing and pulses | The IR has no timing or pulse layer. |
| `gphase` | Global phase is not represented. |

---

## 7. Open items

1. Bits across kernel boundaries: `bit` parameters, returned bits, and outer bits inside arms and loop bodies.
2. Implicit copying of a bit that is read more than once.
3. `default`, which needs support in `select`.
4. `gate` declarations and gate modifiers.
5. `break` and `continue`.
