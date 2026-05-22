# qstack MLIR Refactor — Design Specification

## 1. What This Refactor Does

This refactor changes qstack's internal IR and compiler architecture. The user-facing programming model — kernels and host-language callbacks — is unchanged.

### 1.1 What does not change

1. **The qstack thesis.** Purely quantum IR, opaque classical callbacks, compositional compiler passes.
2. **Kernels as allocation scopes.** A kernel allocates qubits, operates on them, and measures them before returning. The shape generalizes to multi-allocation and explicit borrows; the role is the same.
3. **Callbacks as the only quantum–classical boundary.** Host-language code is reachable only through named callbacks invoked at measurement points.
4. **The callback registry as the trust boundary.** Decoders and selectors are host-language code registered by symbol name. The compiler does not inspect their bodies.
5. **Pass-based compilation.** Compilation is a sequence of structural rewrites. `Compiler` subclasses with `handlers` dicts become MLIR `Pass`es with `RewritePattern`s.
6. **ISA partitioning.** Each target architecture has its own ISA, realized as a separate MLIR dialect on top of a shared core `qstack` dialect. The four existing ISAs (toy, cliffords, h2, atoms) carry over directly.
7. **Static instruction parameters.** Gate parameters remain static metadata, now as MLIR op attributes instead of `parameters: dict` fields.
8. **The noise model.** Noise lives at the emulator and runtime level, attached to gates via ISA op metadata. It is not in the IR.
9. **The decoder concept.** A QEC pass inserts a decoder between physical measurements and downstream consumers. The mechanism becomes a `qstack.decode` op instead of a `Compiler.decode` hook.
10. **Measurement-consumes-qubit semantics.** Measurement destroys the qubit and yields a classical outcome. In the new IR this is an SSA-level consume.

> TODO: Create a new surface language, or identify how to expose it to openqasm/python.

### 1.2 What does change

What does not survive: the runtime measurement stack; `Compiler.handlers` and `wrap_callbacks`; `QubitId` string-based qubit identity; the single-optional-target `Kernel` dataclass shape; callbacks that return freshly synthesized `Kernel` instances.

At its core, the refactor consists of six changes against the current IR. Everything else in this document is a consequence of one or more of them.

**(a) Adopt MLIR as the IR framework.**
The Python dataclass tree (`Kernel`, `QuantumInstruction`, `ClassicInstruction`, `Program`) is replaced by an MLIR module built from a custom `qstack` dialect together with one dialect per ISA. Compiler passes become MLIR `Pass`es with `RewritePattern`s instead of `Compiler` subclasses with handler dictionaries.

**(b) Linearize qubits.**
`QubitId` references on instruction targets are replaced by SSA values of linear type `!qstack.qubit` that are threaded through gate results and consumed exactly once. A `!qstack.qubit` is a handle — the single-party right to operate on a specific quantum register — not a quantum state. The discipline gives the verifier structural checks on rewriters, makes the use-def chain coincide with the dependency graph, and puts the IR in the canonical form required by ZX-calculus, stabilizer tracking, and region-equivalence checking. See §4.1.

**(c) Linearize and name bits.**
The implicit runtime measurement stack is replaced by explicit SSA values of type `!qstack.bit`, produced by `qstack.measure` and named as operands wherever they are used. Bits are linear (single-use) for the same reasons as qubits: producer–consumer agreement is statically checkable, reordering independent measurements does not perturb other bits, and a decoder's role is to consume physical bits and produce a logical one rather than to fan a bit out. See §4.1.

**(d) Remove JIT kernel compilation.**
Today a callback may return a freshly constructed `Kernel` at run time, which the compiler must JIT-recompile via `wrap_callbacks`. In the new IR, each callback site (`qstack.select`) carries a fixed, named menu of `func.func` continuations chosen at IR-construction time; the callback picks a label. As a consequence, all Kernels that might be used at runtime can be compiled AOT, and the original host-language callback survives any compilation, encoding, or lowering pass unchanged. See §4.3.3.

**(e) Make decoders explicit in the IR.**
Decoder invocation moves out of being a hidden mechanism embedded in a wrapped callback and becomes an explicit `qstack.decode @sym` op inserted by the QEC pass. Where the decoder runs, on which bits, and what it produces are fully transparent in the IR. See §4.3.3.

**(f) Make qubit borrowing explicit.**
The kernel signature is extended to declare not only the bits it produces, but also the qubits it _borrows_ — qubits it uses without allocating, which it must therefore thread back as results. Allocations move from a single `QubitId | None` field to a count `a` of entry-block arguments. Borrowed qubits, today invisible in the kernel header and referenced from the body by outer-scope `QubitId` strings, become an explicit operand list of length `b` returned alongside the bits. The resulting signature `(qubit × b) → (bit × a, qubit × b)` is what enables linearity at the kernel boundary and gives the verifier a mechanically checkable contract for whole-kernel analysis. See §4.2.

---

## 2. An Example

Before the detailed specification, let's present a small program in the new IR alongside a brief walkthrough.

### 2.1 Repeat-until-zero

The example is _heralded |1⟩ preparation_: given a qubit assumed to be in |0⟩, entangle it with a fresh ancilla via `H; CX` (yielding `(|00⟩ + |11⟩)/√2`), then measure the ancilla. On outcome 1, the borrowed qubit has collapsed to |1⟩ and the preparation is done; on 0, it has collapsed to |0⟩ and the procedure is retried. This is a real state-preparation idiom — the structural skeleton of postselection-based ancilla preparation in neutral-atom arrays and of the first step of many magic-state distillation protocols — rather than the toy repeat-until-zero of the original qstack paper.

```mlir
// Identity continuation: pass the qubit through unchanged.
func.func @id(%q: !qstack.qubit) -> !qstack.qubit {
  func.return %q : !qstack.qubit
}

// Host-language selector: declared in MLIR so the symbol table resolves the
// qstack.select reference, but with no body — the implementation lives in
// the host language. The `qstack.selector` attribute marks it as a callback.
func.func private @repeat_until_one(%b: !qstack.bit) attributes { qstack.selector }

// Heralded |1> preparation. Given a borrowed qubit assumed to be in |0>,
// repeatedly entangle with a fresh ancilla and measure the ancilla until
// the outcome is 1 — at which point the borrowed qubit has collapsed to |1>.
func.func @prepare_one(%q0: !qstack.qubit) -> !qstack.qubit {

  // Kernel surfaces its measurement: 1 allocation, 1 bit out, 1 borrow threaded.
  %m, %q0_inner = qstack.kernel(%q0) {
  ^bb0(%q1: !qstack.qubit):
    %q0a       = cliffords.h  %q0
    %q0b, %q1a = cliffords.cx %q0a, %q1
    %meas      = qstack.measure %q1a
    qstack.return %meas, %q0b
  }

  // Selection lives at function scope, consumes the surfaced bit, picks a
  // continuation. Both continuations have uniform signature (qubit) -> qubit.
  %cont = qstack.select @repeat_until_one(b = %m)
    continuations { done = @id, retry = @prepare_one }
    : (!qstack.qubit) -> !qstack.qubit
  %q0_out = func.call_indirect %cont(%q0_inner)
    : (!qstack.qubit) -> !qstack.qubit

  func.return %q0_out : !qstack.qubit
}

// Top-level driver: allocate q0 in |0>, run @prepare_one to land it in |1>,
// measure. The returned bit is provably 1.
func.func @main() -> !qstack.bit {
  %b = qstack.kernel() {
  ^bb0(%q0: !qstack.qubit):
    %q0_one = func.call @prepare_one(%q0) : (!qstack.qubit) -> !qstack.qubit
    %m      = qstack.measure %q0_one
    qstack.return %m
  }
  func.return %b : !qstack.bit
}
```

```python
def repeat_until_one(*, b, done, retry):
    return done if b == 1 else retry
```

### 2.2 How the example works

The IR introduces two types: `!qstack.qubit` (a linear handle to a qubit register) and `!qstack.bit` (a linear classical measurement outcome). Both types are single-use: every SSA value of either type must be consumed exactly once.

Each gate consumes qubit operands and produces fresh qubit results. The post-gate names (`%q0a`, `%q0b`, `%q1a`) refer to the same physical qubits as their predecessors, just at a later point in the computation. The chain of SSA names threading through gates is the IR's representation of register lifetime.

The `qstack.kernel` op scopes an allocation. Its entry block lists allocated qubits as block arguments; borrowed qubits are listed as kernel operands and referenced from the body by their enclosing-scope names. Inside `@prepare_one`, the kernel allocates `%q1` (one block argument) and borrows `%q0` (one operand). It measures `%q1`, returns the resulting bit `%meas` together with the threaded-back `%q0b`. The signature is `(qubit) -> (bit, qubit)`: one allocation produces one surfaced bit; the borrow returns to the caller.

`qstack.measure` is the only core op that consumes a qubit without producing one; it yields a `!qstack.bit`. Kernels surface their measurement bits as results: every allocated qubit is measured exactly once inside the body, and the resulting bits appear in the kernel's result list. Reading the kernel signature is enough to know how many measurements happened inside.

`qstack.select` is the callback site. It lives at function scope — outside the kernel, where the surfaced bit is in scope. It carries a fixed, named menu of `func.func` continuations chosen at IR-construction time; the host-language selector only picks a label. The op yields an SSA value of ordinary MLIR function type — the selected continuation as a callable — which is then invoked by `func.call_indirect`. Here the menu is `{ done = @id, retry = @prepare_one }`: both continuations have signature `(qubit) -> qubit`, matching the select op's declared result type. The selector consumes `%m`; the `func.call_indirect` threads `%q0_inner` into the chosen continuation, which returns the prepared qubit.

Control flow over surfaced bits is the function body's job, not the kernel's. The kernel is reserved for the allocation lifecycle; the selection on its surfaced bit naturally lives one scope above.

Recursion happens through a symbol reference (`@prepare_one`), not through a runtime-synthesized kernel. A QEC pass that rewrites `@prepare_one`'s body therefore picks up the rewrite on every recursive invocation automatically.

---

## 3. Why MLIR

The case for adopting MLIR rests on four technical points and one strategic one.

- **SSA as the compiler substrate.** SSA is the established default for IR design; (b), (c), and (e) all require it.
- **Pass manager and rewrite engine.** `ConversionTarget`, `RewritePattern`, dialect conversion, and pass composition exist and are well-tested. They do not need to be reinvented.
- **Symbol tables and `func.func` reuse.** Function definitions, calls, callback symbols, decoders, and continuation references all use one symbol-resolution mechanism. This directly supports growth of the IR beyond a handful of kernels.
- **Dialects fit qstack's model.** The "one ISA equals one dialect, sharing a common core" partitioning is precisely what MLIR's dialect mechanism is designed for.

Strategically, I'd like to position qstack as a quantum compiler framework rather than a research one-off. MLIR is where the serious quantum compiler stacks have converged: CUDA-Q and Guppy both use MLIR as the high-level IR before lowering to QIR or a runtime ABI. Adopting MLIR places qstack in that conversation by construction and provides a credible backend path (QIR, LLVM, or direct interpretation against a runtime ABI).

The accepted costs are an MLIR build and Python-binding dependency, a steeper contributor onboarding curve, and a less direct step-debugging experience than today's pure-Python tree walker. The emulator must be rewired to consume MLIR instead of the dataclass tree, but this is a one-time implementation cost.

---

## 4. The qstack Dialect

### 4.1 Types

The core qstack dialect introduces exactly two types:

| Type            | Meaning                                                                                     |
| --------------- | ------------------------------------------------------------------------------------------- |
| `!qstack.qubit` | A linear handle to a qubit register. Every value of this type is consumed exactly once.     |
| `!qstack.bit`   | A classical measurement outcome. Linear: every value of this type is consumed exactly once. |

ISA dialects may introduce additional types (e.g., a continuous-angle type for rotation gates). The core dialect introduces no others. Kernels and functions are referenced by symbol name; the dialect provides no first-class kernel or unitary value type.

#### 4.1.1 Linearity

Both `!qstack.qubit` and `!qstack.bit` are linear: every SSA value of either type has exactly one use within its defining region. A qubit is consumed by appearing as an operand of an op that does not list it among its results; a bit is consumed by appearing as an operand of any op that takes a bit, or by the kernel's `qstack.return` terminator. The discipline is enforced by an MLIR op trait carried by every op that touches a qubit or bit, checked by the standard verifier.

A `!qstack.qubit` is a handle — the single-party right to operate on a specific quantum register — not a quantum state. A `!qstack.bit` is a measurement outcome value, never an arbitrary integer.

Linearity provides four properties relevant to qstack's role as a rewriting and verification framework:

1. **Structural verifier checks on rewriters.** A pass that drops a value on the floor, wires two consumers to the same SSA value, or introduces a reference to an out-of-scope value fails the verifier at the pass — not at runtime, and without alias analysis. The current IR enforces these properties only by namespace convention over `QubitId` strings, with no static check.

2. **Use-def chain coincides with the dependency graph.** Peephole patterns (`H; H → I`, commutation, fusion) become local graph matches rather than walks over an instruction list that reconstructs dependencies from string identifiers. For bits, order independence at the IR level follows directly: independent measurements may be reordered freely, and downstream callbacks name which bits they depend on rather than the order in which they were produced.

3. **Canonical form for verification techniques.** The SSA + linear use-def graph is directly a ZX graph (modulo per-op spider expansion). Stabilizer tracking, region-equivalence checking, and quantum Hoare-style reasoning all assume straight-line, no-aliasing dataflow; linearity provides the no-aliasing precondition by construction. The kernel signature `(qubit × b) → (bit × a, qubit × b)` becomes a single-line, machine-readable contract for boundary mapping.

4. **Statically checkable producer–consumer agreement at boundaries.** A selector expecting three named bits and given only two fails the verifier. A bit produced but never consumed fails the verifier, catching "measured but forgot to use" bugs at the pass.

The cost is real: IR text is more verbose, the programmatic builder API is heavier, qstack owns and maintains its own single-use verifier trait, and every rewrite pattern must thread fresh SSA names through gates rather than mutating in place. These costs fall on the people writing the IR builder and the compiler passes, not on end users.

### 4.2 Kernels

A kernel is an allocation scope: it allocates qubits, operates on them, measures them, and returns. `qstack.kernel` is the MLIR op that realizes this concept. It is a region op; its body holds the gates, nested kernels, and measurements that act on the allocated qubits and on any qubits borrowed from the enclosing scope.

The signature was introduced in §1.2(f):

```
qstack.kernel(qubit × b) -> (bit × a, qubit × b)
```

with `a` allocations and `b` borrows.

#### 4.2.1 Signature and invariants

Two invariants govern every `qstack.kernel`:

- **Bits equal allocations.** The kernel produces exactly `a` `!qstack.bit` results, one per allocation. Equivalently, every allocated qubit is measured exactly once inside the body.
- **Borrows in equal borrows out.** The `b` qubits passed as operands are threaded back as the `b` trailing qubit results. Allocated qubits never appear in the result list.

The combinations `n_bits ≠ a` and `qubit_results ≠ b` are forbidden. This is the stack-discipline invariant from which qstack takes its name.

| `a` | `b` | Meaning                                                        |
| --- | --- | -------------------------------------------------------------- |
| 0   | 0   | Empty kernel (rare).                                           |
| 0   | n   | Pure unitary scope (gates on borrowed qubits, no measurement). |
| 1   | n   | Classical allocate-and-measure scope; produces one bit.        |
| k   | n   | Multi-qubit allocate-and-measure scope; produces `k` bits.     |

#### 4.2.2 Allocations and borrows

Allocations appear as block arguments of the body's entry block: `a` block arguments, one per allocated qubit. Borrows appear as operands of the kernel op itself: `b` operands, listed in the same order as the trailing qubit results. The body sees both sets as ordinary SSA values; the distinction is only that allocations originate at the entry block and borrows originate outside the kernel.

A two-ancilla syndrome extraction illustrates the full shape:

```mlir
%s1, %s2, %data1', %data2' = qstack.kernel(%data1, %data2) {
^bb0(%a1: !qstack.qubit, %a2: !qstack.qubit):
  // entangle ancillas with %data1, %data2, then measure ancillas
  %m1 = qstack.measure %a1_final
  %m2 = qstack.measure %a2_final
  qstack.return %m1, %m2, %data1_final, %data2_final
}
```

Two allocations (block arguments), two borrows (operands referenced inline), two bits, two threaded qubits.

The only `!qstack.qubit` values visible inside a kernel are (a) its block arguments and (b) the qubits listed as kernel operands. A qubit defined in an enclosing scope but not named in the operand list is not in scope inside the body — there is no implicit capture of qubits. The kernel's qubit footprint is therefore readable from its signature alone.

Listing a borrowed qubit in the operand list is a scope declaration, not a use: the qubit's single linear use is the one inside the body.

`!qstack.bit` values from the enclosing scope may be referenced freely inside a kernel — they do not appear in the operand list — but each such reference counts as the single use of that bit. A bit captured by a kernel cannot also be used outside the kernel.

### 4.3 Core ops

#### 4.3.1 `qstack.measure`

**Signature.** `(!qstack.qubit) -> !qstack.bit`. Consumes the qubit; produces a bit.

**Placement.** `qstack.measure` may appear only inside the body of a `qstack.kernel` with at least one allocation. It may not appear at the top level of a `func.func`. Joint or non-destructive measurements live in ISA dialects, not in the core.

**No identity tracking of allocations to measurements.** The operand to a measure may be any qubit in scope — an allocated block argument, a borrowed qubit, or any threaded descendant. The kernel's contract requires that the body perform exactly as many qubit-consuming measurements as it has allocations, but does not require that any particular qubit be measured for any particular allocation. This flexibility is necessary for teleportation-style patterns: in gate teleportation and lattice-surgery state injection, the logical state migrates from the input qubit to a freshly allocated ancilla, and the input is then measured.

**The bit need not flow directly into `qstack.return`.** A measured bit is an ordinary SSA value. It may feed into `qstack.decode`, into `qstack.select`, or be used in several places before the kernel returns.

#### 4.3.2 Gates thread qubits

A gate consumes qubits as operands and produces fresh `!qstack.qubit` SSA values as results. A Hadamard has the form:

```mlir
%q1 = cliffords.h %q0 : (!qstack.qubit) -> !qstack.qubit
```

A CNOT has the form:

```mlir
%c1, %t1 = cliffords.cx %c0, %t0 : (!qstack.qubit, !qstack.qubit) -> (!qstack.qubit, !qstack.qubit)
```

The post-gate names are fresh SSA values that refer to the same physical qubits at a later point in time. This is the meaning of "threading": the same physical resource is denoted by a chain of SSA values, each used exactly once.

#### 4.3.3 `qstack.select` and `qstack.decode`

These two ops are the only places in the IR where control or data crosses from the quantum domain into host-language code. Both take `!qstack.bit` operands and are opaque to the compiler: their bodies live in the host language, registered by symbol name. There is no measurement stack and no implicit context; every classical input is a named operand and every classical output is an SSA value.

##### `qstack.select`

`qstack.select` invokes a host-language selector on a bundle of named bits. The selector chooses one entry from a fixed, named menu of `func.func` continuations declared on the op itself. The op's result is that entry as an SSA value of MLIR function type; a subsequent `func.call_indirect` invokes it. This is the form every classical control decision takes — repeat-until-success, syndrome-conditioned branching, mid-circuit halts — and replaces the previous mechanism of callbacks returning freshly constructed kernels.

Selection and invocation are two distinct steps:

```mlir
// 1. Run the host callback on the named bit operands; it returns one of the
//    menu entries as an SSA value of MLIR function type.
%cont = qstack.select @callback(name1 = %b1, name2 = %b2, ...)
    continuations { label_a = @sym_a, label_b = @sym_b, ... }
    : (bit × j, qubit × n) -> (bit × k, qubit × n)

// 2. Invoke the chosen continuation, passing the operands every continuation
//    needs to run.
%bits..., %qubits... = func.call_indirect %cont(%b_in..., %q_in...)
    : (bit × j, qubit × n) -> (bit × k, qubit × n)
```

**Operands.** Named bit operands (`name = %b`) of `!qstack.bit` consumed by the selector to pick a label. The select op takes no quantum operands and no operands intended for the continuation; everything the chosen continuation needs flows through `func.call_indirect`.

**Result.** A single SSA value of MLIR function type — the chosen continuation as a callable. The signature is declared on the select op and is the same for every menu entry.

**Continuation menu.** A named dictionary mapping labels to `func.func` symbols. All entries must have the declared signature; there is no per-entry pre-binding of operands. (Per-entry pre-binding would be unsound under linear bits: a value pre-bound into one menu entry would be silently dropped whenever the selector picked a different entry.) Any per-branch classical data must be encoded inside the continuation symbol's body.

The menu is fixed at IR-construction time as a finite, named set of `func.func` symbols. The selector cannot construct a fresh kernel at runtime. As a consequence, every continuation that can ever fire is a symbol in the module, the compiler does not need to be reachable at runtime, and reachability and dead-code analyses are standard symbol-table walks. Patterns where the next quantum circuit is genuinely unknown until runtime cannot be expressed; for select-on-bit patterns (QEC corrections, repeat-until-success, teleportation, lattice-surgery decisions), this is acceptable.

**Runtime semantics.**

1. The named bit operands are resolved to concrete values, consuming them.
2. The selector's registered host-language function is invoked with the named classical values and the names of the continuations.
3. It returns one of the continuation names. The runtime materializes the corresponding `func.func` symbol as a function value and yields it as the op's result.
4. The following `func.call_indirect` invokes that function value with the operands every continuation requires. The continuation's results become the call's results.

**Symbol declaration.** Every selector symbol referenced by a `qstack.select` op must exist in the module's symbol table. The convention is a body-less `func.func private` declaration carrying the `qstack.selector` attribute:

```mlir
func.func private @my_selector(%b1: !qstack.bit, %b2: !qstack.bit)
    attributes { qstack.selector }
```

The declaration's parameter list mirrors the named bit operands; parameter names match the named-operand keys used at call sites. There is no MLIR result, because the selector returns a continuation label (consumed by the runtime trampoline) rather than a value the host code constructs. The host-language implementation is registered separately, keyed by symbol name. The module-level verifier checks the attribute, the empty body, and that every named operand on a `qstack.select @sym(...)` matches a parameter of `@sym`'s declaration.

##### `qstack.decode`

`qstack.decode` invokes a host-language decoder on a bundle of bits and produces a single `!qstack.bit`. It is used for syndrome decoding, parity computations, and any other pure classical bit-to-bit transformation. Unlike `qstack.select`, it has no menu and chooses no continuation; it is a function call whose body the compiler does not inspect.

```mlir
%logical = qstack.decode @majority_vote(%p1, %p2, %p3)
    : (!qstack.bit, !qstack.bit, !qstack.bit) -> !qstack.bit
```

**Signature.** `(!qstack.bit × k) -> !qstack.bit` for `k ≥ 1`. The op has no quantum effect and no placement restriction.

Decoders are inserted by compiler passes — most commonly a QEC encoding pass that turns one logical measurement into several physical measurements and routes them through a `qstack.decode @majority_vote` so that downstream callbacks see the unchanged SSA bit.

**Symbol declaration.** As with selectors, every decoder symbol must exist in the module's symbol table. The convention is a body-less `func.func private` carrying the `qstack.decoder` attribute, with the bit operand list as parameters and a single `!qstack.bit` result:

```mlir
func.func private @majority_vote(!qstack.bit, !qstack.bit, !qstack.bit) -> !qstack.bit
    attributes { qstack.decoder }
```

Unlike selectors, decoders do have an MLIR result type — the produced bit is a real SSA value. The host-language implementation is registered separately, keyed by symbol name.

### 4.4 Functions reuse `func.func`

A qstack function is a `func.func` whose signature mentions `!qstack.qubit` or `!qstack.bit`, and whose body contains qstack and ISA-dialect ops. Direct invocation uses `func.call`. The qstack dialect contributes no replacement for either.

```mlir
func.func @bell(%a: !qstack.qubit, %b: !qstack.qubit)
    -> (!qstack.qubit, !qstack.qubit) {
  %a1       = cliffords.h  %a
  %a2, %b1  = cliffords.cx %a1, %b
  func.return %a2, %b1 : !qstack.qubit, !qstack.qubit
}
```

This function borrows both of its qubits from the caller and threads them back out; it allocates nothing of its own, so no `qstack.kernel` is required. A function that needs fresh qubits wraps the allocation in a `qstack.kernel` inside its body.

Reuse provides symbol-table machinery, callable-interface plumbing, function-type printing and parsing, and compatibility with MLIR's `func`-aware tooling. The cost is that qstack's function-level invariants — qubit conservation at the boundary, no top-level `qstack.measure` — cannot live in `func.func`'s op verifier; they are checked by a module-level verifier pass that walks every `func.func` whose signature or body involves qstack types.

### 4.5 Design decisions

This section records non-obvious choices in the dialect and their rationale, deferred from the main exposition to keep the flow on _what the dialect is_ rather than _what it could have been_.

#### 4.5.1 Why not `!i1` for bits

A measurement outcome is not necessarily a Boolean. On hardware that suffers atom loss, leakage, or other escape-from-computational-subspace failure modes (neutral-atom arrays, trapped ions in some regimes), a measurement may return a third value — _lost_ or _null_ — distinct from both `0` and `1`. A dedicated `!qstack.bit` type allows this representation to widen later (to `0 | 1 | lost`, or to soft information such as a log-likelihood ratio for a syndrome decoder) without modifying every signature.

The dedicated type also marks the quantum-classical boundary structurally: a `!qstack.bit` value is by construction produced by `qstack.measure`, an ISA measurement op, or a `qstack.decode` — never by inline `arith.*` on arbitrary integers. The purely-quantum-IR principle is preserved by typing alone.

#### 4.5.2 Closed continuation menu

A `qstack.select` op's menu is fixed at IR-construction time as a finite, named set of `func.func` symbols. The host-language selector chooses among them by returning a label; it cannot construct a fresh kernel at runtime. This is a deliberate trade of expressiveness for static reasoning, justified by four properties:

1. **Fully static, closed-universe compilation.** Every continuation that can ever fire is a symbol in the module. The compiler does not need to be reachable at runtime; there is no `wrap_callbacks` and no JIT-recompile loop. Reachability analysis, dead-code analysis, and per-function pass scheduling are standard symbol-table walks.

2. **Clean separation between choice and code.** A selector is a function from bits to a label. Continuations are quantum code. The two artifacts are authored and tested in isolation; the person writing the selector needs to know what each continuation does well enough to choose correctly but does not need to build it.

3. **Callbacks survive compilation unchanged.** The selector's host-language function is never modified, and the continuation `func.func` symbols it references retain their names and signatures across every pass. A continuation's body may have its quantum content rewritten by normal ISA-lowering passes (as for any other `func.func` body containing quantum code), but the selector's menu still points at the same symbols with the same external contracts.

4. **Decoupled compiler and runtime.** No recursive callback-into-compiler. Standard pipeline shape: closed module in, executable out.

**Accepted cost.** Patterns where the next quantum circuit is genuinely unknown until runtime — synthesizing an arbitrary circuit at runtime from classical data — cannot be expressed. For select-on-bit patterns (QEC corrections, repeat-until-success, teleportation, lattice-surgery decisions), this is acceptable; for genuinely runtime-synthesized circuits, the IR is not the right tool.

#### 4.5.3 No global classical state

There is no measurement stack and no implicit context. Every classical input to a callback is a named operand; every classical output is an SSA value. Scoping is SSA dominance, which coincides with region nesting. The verifier never has to chase a runtime side-channel.

#### 4.5.4 Selection and invocation as separate ops

`qstack.select` could have fused selection and invocation into a single op whose results are the chosen continuation's results. Instead, the select op yields the chosen continuation as an SSA value of MLIR function type, and a subsequent `func.call_indirect` invokes it. The split reflects the conceptual model directly: the callback returns a continuation, not a value computed from quantum operands. It also separates two distinct concerns — the host-language choice and the quantum invocation — so a pass can rewrite the invoke (for example, specialize a single-entry menu) without touching the callback. Qubit operands move to `func.call_indirect`, leaving `qstack.select` with classical operands only.

#### 4.5.5 No `!qstack.continuation` type

A dedicated continuation type was considered as the result of `qstack.select`. It was rejected: the continuation is already a `func.func` symbol, and MLIR's plain function type `(...) -> (...)` together with `func.call_indirect` provides exactly the needed semantics. Adding a new type would duplicate the function-type/callable-interface machinery without buying anything that the verifier cannot already check (menu-entry signature equality is a one-line rule on the select op).

#### 4.5.6 Variadic operands instead of a qubit-array type

The core dialect intentionally has no array-of-qubits value type. Multiple qubits are carried as variadic operands and results; an op that takes `n` qubits has `n` SSA values of type `!qstack.qubit`. Aggregate types (`tensor`, `memref`, `vector`) carry storage and aliasing semantics that contradict linear qubit ownership; a tuple-like type would defeat per-element linearity tracking.

Logical resources that naturally aggregate many physical qubits — surface-code patches, color-code blocks, concatenated qubits — are expressed as values of dedicated types in higher-level dialects (for example, `!surface.patch<d>`), with their own ops. A lowering pass expands such an aggregate value into its physical qubits inside a `qstack.kernel` when the IR drops to the physical level. The core qstack dialect remains free of aggregate qubit machinery.
