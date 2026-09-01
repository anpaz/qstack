# qstack MLIR Refactor — Design Specification

## 1. Scope

This document specifies qstack's executable IR and its noiseless semantics.

qstack is a quantum IR with opaque host-language callbacks. A program is a closed collection of named kernels rooted at `@main`; quantum work is expressed only in those kernels, and the host is reached only through explicit `qstack.select` and `qstack.decode` operations. Compiler passes transform one closed module into another and do not inspect registered host callback implementations.

Textual syntax in this document is the syntax the implementation actually parses and prints. Blocks fenced as `mlir` are complete modules that parse and pass `qstack.verifier.verify_module`; blocks fenced as `text` are syntax templates with placeholders.

### 1.1 Principles

1. **A program is rooted at a kernel.** A module has exactly one entry kernel, `qstack.kernel @main`; executing it executes the statically reachable collection of kernels that makes up the program.
2. **A kernel is a quantum instrument.** It maps its borrowed qubits and bits to its declared results, producing classical outcomes along the way. It is the only construct that creates qubits, and its allocation count is a detail of how the instrument is realized, not part of what it means.
3. **The core is quantum plus explicit callback boundaries.** A kernel contains only target-dialect unitaries, measurement, decoding, selection, and calls to other kernels.
4. **Qubits and bits are linear.** Each is used once. Gates thread a qubit to a new SSA name; measurement is the only core qubit destructor.
5. **Existing callbacks are fixed interfaces.** A callback is registered by symbol name and may be stateful: its output and next state are determined by its current state and received values. All callbacks execute against one stateful host machine and may share its state, so the preserved trace is the single global interleaving of every callback invocation, not a per-symbol order. A pass never changes an existing callback invocation's interface or runtime trace. A callback introduced by a pass is fresh and carries a finite classical obligation derived by semantic verification.

### 1.2 Noiseless scope

This specification makes no claim about code distance, fault tolerance, faulty syndrome extraction, or a noise model.

[`verification-design.md`](verification-design.md) anticipates an _error tag_ on a select case that identifies the error the case is intended to correct, supporting a local, noiseless correctness obligation. **The error tag is specified but not implemented.** `qstack.select` currently carries a callee, bit operands, case arguments, and a case map, and nothing else; there is no attribute for a tag and no verifier rule that reads one. A future noisy design may give the tag a stronger meaning without changing the kernel/callback model below.

## 2. Module and kernel model

A module contains only named `qstack.kernel` definitions and `qstack.selector`/`qstack.decoder` declarations. Exactly one kernel is named `@main`; it has no kernel arguments. Private kernels may be called directly or selected as cases. Every invocation target is therefore statically known, although not every declared kernel need be reachable from `@main`. No other executable top-level construct exists.

### 2.1 Named kernel definitions

A kernel declares its borrowed input types, its allocation count, and its result types:

```text
qstack.kernel @name <[input-types], [result-types]> allocates N {
^bb0(%borrowed..., %fresh...):
    // kernel body
    qstack.return %results... : result-types
}
```

The signature is an attribute on the kernel (`!qstack.kernel_signature`, a pair of type lists), not a value the IR can pass around. A kernel is reached only by naming it in a `qstack.call`, so nothing holds a kernel as an operand and there is no indirect call. The signature carries **types only**: parameters are not named in it, and they correspond positionally to the entry-block arguments.

A kernel definition produces no values of its own, even when its signature declares results. Results appear at the call site, one set per invocation, because a kernel may be called any number of times. Code that needs a kernel's declared results reads `KernelOp.declared_result_types`. The inherited xDSL accessor `Operation.result_types` answers a different question, namely which values this operation itself defines, and correctly reports none.

The declared inputs and the first entry-block arguments correspond positionally. The final `N` entry arguments are fresh `|0⟩` qubits supplied by the kernel invocation, not caller operands.

Arguments and results may contain `!qstack.qubit` and `!qstack.bit`. A qubit result may come from a borrowed input or a fresh allocation. A measurement bit may be returned or consumed by `decode` or `select`.

### 2.2 Kernel calls

`qstack.call` is the only direct invocation operation:

```text
%results... = qstack.call @name(%args...) : (argument-types) -> (result-types)
```

It names a `qstack.kernel`, supplies exactly its declared arguments, and yields exactly its declared results, in the callee's declared order. There is no bit-before-qubit or qubit-before-bit convention: result order is whatever the callee's signature says. Recursive and mutually recursive kernel calls are ordinary symbol references; no call targets arbitrary host or MLIR code.

### 2.3 Permitted body operations

Other than its `qstack.return` terminator, a kernel body may contain only:

1. a unitary operation from the external dialect active at that layer;
2. `qstack.measure`;
3. `qstack.decode`;
4. `qstack.select`; and
5. `qstack.call`.

No generic control flow, arithmetic, memory, arbitrary MLIR operation, or standalone allocation operation is permitted. Classical computation is either an opaque callback boundary or belongs to a future, separately specified dialect.

"A unitary operation from the external dialect" is a structural test, not a fixed list: an operation is a unitary if it satisfies the `UnitaryGateOp` protocol, meaning it exposes a `unitary()` method returning its matrix in standard operand order. The target dialects shipped today are `toy`, `cliffords`, `h2`, and `atoms`, registered in `qstack.dialect.registry`; `register_isa_dialect` admits more without changing the core. A unitary threads its qubit operands to successor results positionally, which is what lets the verifier follow a qubit along its chain.

### 2.4 Structural rules

The executable-IR verifier is intentionally structural: it establishes the IR invariants execution depends on, and does not compare the semantics of a pass's input and output. Beyond the rules stated above, it is required to enforce:

- The module's top level contains only `qstack.kernel`, `qstack.selector`, and `qstack.decoder`, and symbol names are unique across all three.
- A kernel body has exactly one block, and no operation in it carries a nested region.
- `@main` has no borrowed inputs and cannot return a qubit. Its declared results are bits, which are the program's observable output.
- The entry block's argument types equal the declared inputs followed by exactly `allocates N` qubits, and `qstack.return`'s operand types equal the declared result types.
- `allocates` is non-negative, and a kernel body contains exactly one `qstack.return`, its final operation.
- `qstack.measure` consumes a qubit, and the bit operands of `qstack.decode` and `qstack.select` are bits.

### 2.5 Kernel graphs and instruments

A kernel body denotes a dataflow graph: operations are nodes, linear SSA values are wires, borrowed and fresh values are sources, and `qstack.return` is the sink. A call is an opaque node in its caller's graph; its callee is a separate graph. A select similarly refers to separate case-kernel graphs.

Two bodies have the same graph when their nodes, symbols, attributes, and wiring match. The textual order of operations connected by no wire is not semantic in the noiseless model. Callback order is the exception: the derived host wire in Section 4.4 records the global order of stateful host interactions.

A kernel denotes a quantum instrument from its declared borrowed inputs to its declared results. Fresh qubits begin inside an invocation in `|0⟩`; internal measurement outcomes consumed by a decode or select do not cross the kernel boundary. Returned bits carry their probabilities, returned qubits carry their conditional states, and correlations between them are part of the instrument. Calls and selects compose the instruments of their named kernels into the caller's instrument.

## 3. Types and linearity

| Type            | Meaning                                      |
| --------------- | -------------------------------------------- |
| `!qstack.qubit` | A single-party handle to one qubit register. |
| `!qstack.bit`   | A classical measurement outcome.             |

Both types are linear: every SSA value has exactly one use. Unitaries and calls thread qubits to successor values; measurement consumes a qubit and produces a bit. Bits are consumed by decoding, selection, a kernel call, or kernel return.

Within a kernel body, every borrowed or fresh qubit is consumed exactly once: by a unitary, measurement, call, select, or return. Calls and selects may transfer ownership across kernel boundaries, including returning a qubit allocated by the invoked kernel, so qubit conservation is a property of the composed invocation rather than a count of only the caller's local measurements and results. There is no aliasing, implicit copying, or silent discard.

Linearity forbids aliasing and implicit copying. It lets the verifier establish qubit conservation and identify the exact classical values delivered to a callback. The core has no first-class function, continuation, qubit-array, or unitary type.

## 4. Callback declarations and operations

Callbacks are host-language implementations registered by module symbol name. Their bodies are absent from qstack IR; the registry is the only quantum/classical boundary.

### 4.1 Declarations

A callback declaration carries a symbol name and the size of the bit bundle it receives:

```text
qstack.selector @repeat_until_one arity 1
qstack.decoder @majority_vote arity 3
```

Types are not written: every callback input is a `!qstack.bit`, a decoder always returns exactly one bit, and a selector returns a case label to the runtime rather than an SSA value. A decoder must declare at least one input; a selector may declare none, since a stateful selector can still choose a case from its own state alone. Declarations have no body and cannot be kernel-call targets. Selector and decoder implementations occupy separate runtime registry namespaces, but their declarations share the module's qstack symbol namespace, so a valid module cannot declare the same string as both.

The declaration names no parameters, because there are none to bind. Both kinds of callback receive their bits as a single positional tuple of `int`, in operand order, so the host implementation is `def callback(bits)` in either case. Nothing downstream of the declaration repeats an input name, and no invocation site carries one.

### 4.2 Decode

```text
%logical = qstack.decode @decoder(%b0, %b1, ...)
```

`qstack.decode` invokes an opaque decoder, consuming its full bit bundle and yielding a bit. The operand count must equal the declaration's input count. Its explicit operands make it impossible to hide decoding in a wrapper callback. Because both operand and result types are fixed as `!qstack.bit`, no type signature is printed. The runtime delivers the bundle to the registered decoder as one tuple in operand order.

```mlir
builtin.module {
  qstack.decoder @majority_vote arity 3
  qstack.kernel @main <[], [!qstack.bit]> allocates 3 {
  ^bb0(%0: !qstack.qubit, %1: !qstack.qubit, %2: !qstack.qubit):
    %3 = cliffords.h %0
    %4, %5 = cliffords.cx %3, %1
    %6, %7 = cliffords.cx %4, %2
    %8 = qstack.measure %6
    %9 = qstack.measure %5
    %10 = qstack.measure %7
    %11 = qstack.decode @majority_vote(%8, %9, %10)
    qstack.return %11 : !qstack.bit
  }
}
```

### 4.3 Select and direct case invocation

```text
%results... = qstack.select @selector(%bits...) [%case_args...]
    {label = @kernel, ...} : (case-argument-types) -> (case-result-types)
```

The selector consumes bit operands and returns one of its finite case labels. The selected case kernel is invoked directly with `%case_args...`.

Bit operands are positional and their count must match the selector's declared arity. The runtime delivers them to the host callback as one tuple, exactly as it does for a decoder. Every case names a `qstack.kernel` whose declared inputs match `%case_args...` and whose declared results match the select's results, so the select has one known result signature. The callback cannot synthesize a new kernel at runtime. This closed case menu is a validation boundary: the verifier can inspect every quantum behavior the callback may select, while the callback may choose only among those already validated kernels.

Selection and invocation are deliberately one operation. There is no function-valued result, continuation type, or indirect invocation operation.

### 4.4 Callback preservation

For every callback invocation already present in a pass input, compilation must preserve:

- callback symbol and declaration signature;
- selector arity, bit operand order, and finite case map;
- corresponding runtime bit values;
- invocation order and multiplicity; and
- reachability, including correlations with surviving quantum state.

The compiler does not inspect callback code. A callback is a deterministic stateful computation: its output and next state are fixed by its current state and input values. Preserving the symbol and input values alone is therefore insufficient; order and multiplicity preserve the callback's state evolution as well. Because all callbacks run on one host machine and may share state, the preserved order is global, across different callback symbols, not merely among invocations of the same symbol.

This order is represented semantically by the derived **host wire**. It threads through every `decode` and `select`, and through every call whose callee transitively invokes a callback. It is not printed in the IR. Operations unconnected by an SSA wire may otherwise be reordered without changing the kernel graph, but moving a pre-existing callback along the host wire changes program behavior.

A semantic pass verifier checks callback preservation from the source module, target module, and pass witness. A pre-existing callback use must be an identity claim or part of an exact inline copy; a pass cannot wrap, retarget, change, drop, duplicate, or add a use of a callback declared in its source module. Exact inlining may copy the static operation while preserving the runtime trace, because an execution takes either the original call or the inline copy, never both.

A callback introduced by a pass must use a declaration and use fresh relative to the source module. A new decoder appears only in the representation relation's measurement rule; a new selector appears only in a rule's target body. Its required finite behavior is derived as a classical obligation, including the requirement that its implementation not read or write state observed by other callbacks. The full witness conditions and obligation handoff are specified in [`verification-design.md`](verification-design.md).

### 4.5 Semantic pass verification

Executable-IR verification and pass verification are separate checks. The former validates one closed module structurally. The latter checks a source module, target module, and pass-produced witness together, and returns VERIFIED, VERIFIED MODULO CLASSICAL OBLIGATIONS, REFUTED, or UNSUPPORTED.

A witness records the pass's encoding isometry and partitions the source and target graphs into identity, inline, and sub-graph claims. Together with bit equality, the isometry induces the representation relation; reusable rules justify sub-graph claims, and the relation supplies its own allocation and measurement rules. Each source-target kernel pair is checked independently, and the local results compose through calls to the claim about `@main`. Rewrites outside this claim vocabulary are unsupported rather than accepted by whole-program guessing. The complete contract, including its known limitations, is specified in [`verification-design.md`](verification-design.md).

## 5. Example: repeat until one

```mlir
builtin.module {
  qstack.selector @repeat_until_one arity 1
  qstack.kernel @id <[!qstack.qubit], [!qstack.qubit]> allocates 0 {
  ^bb0(%0: !qstack.qubit):
    qstack.return %0 : !qstack.qubit
  }
  qstack.kernel @prepare_one <[!qstack.qubit], [!qstack.qubit]> allocates 1 {
  ^bb0(%0: !qstack.qubit, %1: !qstack.qubit):
    %2 = cliffords.h %0
    %3, %4 = cliffords.cx %2, %1
    %5 = qstack.measure %4
    %6 = qstack.select @repeat_until_one(%5) [%3] {done = @id, retry = @prepare_one} : (!qstack.qubit) -> !qstack.qubit
    qstack.return %6 : !qstack.qubit
  }
  qstack.kernel @main <[], [!qstack.bit]> allocates 1 {
  ^bb0(%0: !qstack.qubit):
    %1 = qstack.call @prepare_one(%0) : (!qstack.qubit) -> !qstack.qubit
    %2 = qstack.measure %1
    qstack.return %2 : !qstack.bit
  }
}
```

`@main` allocates `%0`; `@prepare_one` allocates its own `%1` and measures it, returning the qubit it borrowed. The selector executes inside the kernel where `%5` is measured. Every possible continuation is a named kernel, so the module is closed for ahead-of-time compilation.

After a repetition-code transformation, physical measurement bits are decoded inside the transformed kernel before the unchanged source selector consumes the logical bit. No function-scope plumbing and no callback wrapper are required.

## 6. MLIR role

MLIR remains the substrate for SSA, rewriting, symbol tables, and dialect composition. qstack does not reuse MLIR's function dialect for executable quantum code: the qstack dialect owns its kernel and callback symbols. The implementation is built on xDSL.

## 7. Design and implementation status

The following parts of this design are implemented:

- **Parser and printer syntax.** Every core operation has custom textual syntax and round-trips. `qstack.kernel` uses hand-written `parse`/`print`; the rest use declarative assembly formats.
- **Executable-IR verifier.** `qstack.verifier.verify_module` enforces the current structural, linearity, declaration, and signature-compatibility rules.
- **Runtime.** A `Machine(module, num_qubits=..., registry=..., seed=..., noise=..., qpu=...)` evaluates `@main` shot by shot against a `CallbackRegistry`, over a statevector or Stim backend.
- **Surface language.** QSTACKQASM is a parsed surface syntax with `extern selector`/`extern` declarations, `switch`/`case` continuations, and per-ISA `.inc` includes; it lowers to the IR above.

The implementation has not yet been updated for the reviewed pass-verification design:

- **Witness-producing passes and semantic verification.** Passes do not yet emit representation relations, rules, or claims, and there is no checker for them or for the derived host wire.
- **Fresh generated callbacks.** The repetition-code and Steane passes currently use reserved canonical callback symbols and may reuse matching declarations from their source module. They must instead generate fresh declarations and uses for each transformation. Steane must do so for both its decoder and syndrome selector.
- **Error tags** on select cases, described in Section 1.2 and in `verification-design.md`.
- **Callback-obligation data format**, the artifact a pass emits for a classical verifier to discharge.
- **Noisy semantics**, including any fault-tolerance claim.

Verifier backends, witness serialization, additional claim types, and the other deliberately deferred choices are listed in Section 5 of [`verification-design.md`](verification-design.md).
