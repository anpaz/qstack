# qstack MLIR Refactor — Design Specification

## 1. Scope

This document specifies qstack's executable IR and its noiseless semantics.

qstack is a quantum IR with opaque host-language callbacks. Quantum work is expressed only in named kernels; the host is reached only through explicit `qstack.select` and `qstack.decode` operations. Compiler passes transform a closed module into another closed module and do not inspect, wrap, or replace registered host callback implementations.

### 1.1 Principles

1. **A program is a kernel.** A module has exactly one entry kernel, `qstack.kernel @main`; executing it executes the program.
2. **A kernel is an allocation scope.** It is the only construct that creates qubits, and every fresh qubit dies within that kernel invocation.
3. **The core is quantum plus explicit callback boundaries.** A kernel contains only target-dialect unitaries, measurement, decoding, selection, and calls to other kernels.
4. **Qubits and bits are linear.** Each is used once. Gates thread a qubit to a new SSA name; measurement is the only core qubit destructor.
5. **Callbacks are fixed, opaque, and deterministic.** A callback is registered by symbol name and may be stateful: its output and next state are determined by its current state and received values. A pass never changes an existing callback invocation's interface or trace, including its order and multiplicity.

### 1.2 Noiseless scope

This specification makes no claim about code distance, fault tolerance, faulty syndrome extraction, or a noise model. A correction case may carry an error tag that identifies the error it is intended to correct. The tag supports a local, noiseless correctness obligation only; a future noisy design may give it a stronger meaning without changing the kernel/callback model below.

## 2. Module and kernel model

A module contains only named `qstack.kernel` definitions and `qstack.selector`/`qstack.decoder` declarations. Exactly one kernel is named `@main`; it has no kernel arguments. Private kernels may be called directly or selected as cases. No other executable top-level construct exists.

### 2.1 Named kernel definitions

A kernel explicitly declares its borrowed inputs, allocation count, and results:

```mlir
qstack.kernel @name(%borrowed: !qstack.qubit, ...)
    allocates N
    -> (result-types) {
  ^bb0(%borrowed: !qstack.qubit, ..., %fresh0: !qstack.qubit, ...):
    // kernel body
    qstack.return ...
}
```

The declared inputs and the first entry-block arguments correspond positionally. The final `N` entry arguments are fresh `|0⟩` qubits supplied by the kernel invocation, not caller operands.

Arguments and results may contain `!qstack.qubit` and `!qstack.bit`. A borrowed qubit may be threaded back as a result or consumed by measurement. A qubit result must descend from a borrowed input: a fresh allocation never escapes as a qubit result. A measured bit may be returned or consumed internally by `decode` or `select`.

There is no returned-bit-count invariant. Instead, every fresh qubit must be consumed by a measurement before the kernel returns. The only qubit destructor is `qstack.measure`; there is no silent discard. Consumed borrows are therefore ordinary inputs that do not appear among the returned qubits.

### 2.2 Kernel calls

`qstack.call` is the only direct invocation operation:

```mlir
%bits..., %qubits... = qstack.call @name(%args...)
    : (argument-types) -> (result-types)
```

It names a `qstack.kernel`, supplies exactly its declared arguments, and yields exactly its declared results. Recursive and mutually recursive kernel calls are ordinary symbol references; no call targets arbitrary host or MLIR code.

### 2.3 Permitted body operations

Other than its `qstack.return` terminator, a kernel body may contain only:

1. a unitary operation from the external dialect active at that layer;
2. `qstack.measure`;
3. `qstack.decode`;
4. `qstack.select`; and
5. `qstack.call`.

No generic control flow, arithmetic, memory, arbitrary MLIR operation, or standalone allocation operation is permitted. Classical computation is either an opaque callback boundary or belongs to a future, separately specified dialect.

## 3. Types and linearity

| Type            | Meaning                                      |
| --------------- | -------------------------------------------- |
| `!qstack.qubit` | A single-party handle to one qubit register. |
| `!qstack.bit`   | A classical measurement outcome.             |

Both types are linear: every SSA value has exactly one use. Unitaries consume qubit handles and return successor handles. Measurement consumes a qubit and produces a bit. Bits are consumed by decoding, selection, a kernel call, or kernel return.

Linearity forbids aliasing, implicit copying, and silent discard. Together with fresh-qubit provenance, it lets a verifier establish allocation non-escape and identify the exact classical values delivered to a callback. The core has no first-class function, continuation, qubit-array, or unitary type.

## 4. Callback declarations and operations

Callbacks are host-language implementations registered by module symbol name. Their bodies are absent from qstack IR; the registry is the only quantum/classical boundary.

### 4.1 Declarations

```mlir
qstack.selector @repeat_until_one(%b: !qstack.bit)

qstack.decoder @majority_vote(
    %b0: !qstack.bit, %b1: !qstack.bit, %b2: !qstack.bit
) -> !qstack.bit
```

A selector declaration has named bit inputs and returns a case label to the runtime, not an SSA value. A decoder consumes one or more bits and produces one bit. Declarations have no body and cannot be kernel-call targets.

### 4.2 Decode

```mlir
%logical = qstack.decode @majority_vote(%p0, %p1, %p2)
    : (!qstack.bit, !qstack.bit, !qstack.bit) -> !qstack.bit
```

`qstack.decode` invokes an opaque decoder, consuming its full bit bundle and yielding a bit. Its explicit operands make it impossible to hide decoding in a wrapper callback.

### 4.3 Select and direct case invocation

```mlir
%results... = qstack.select @repeat_until_one(b = %measurement)
    cases { done = @id, retry = @prepare_one }
    (%case_args...) : (case-argument-types) -> (case-result-types)
```

The selector consumes named bit operands and returns one of its finite case labels. The selected case kernel is invoked directly with `%case_args...`. Every case names a `qstack.kernel` with the same declared arguments and results, so the select has one known result signature. A case may carry an error tag identifying the error it is intended to correct. The callback cannot synthesize a new kernel at runtime. This closed case menu is a validation boundary: the verifier can inspect every quantum behavior the callback may select, while the callback may choose only among those already validated kernels.

Selection and invocation are deliberately one operation. There is no function-valued result, continuation type, or indirect invocation operation.

### 4.4 Callback preservation

For every callback invocation already present in a pass input, compilation must preserve:

- callback symbol and declaration signature;
- selector input names and finite case map;
- corresponding runtime bit values;
- invocation order and multiplicity; and
- reachability, including correlations with surviving quantum state.

The compiler does not inspect callback code. A callback is a deterministic stateful computation: its output and next state are fixed by its current state and input values. Preserving the symbol and input values alone is therefore insufficient; order and multiplicity preserve the callback's state evolution as well. A pass may add an explicit decoder or a local selection construct only under a fresh callback declaration. It never wraps, retargets, changes, or adds a use of a pre-existing callback: another use would change that callback's invocation trace. The verification design specifies the classical obligations reported for newly introduced callback uses.

## 5. Example: repeat until one

```mlir
qstack.selector @repeat_until_one(%b: !qstack.bit)

qstack.kernel @id(%q: !qstack.qubit)
    allocates 0
    -> !qstack.qubit {
  ^bb0(%q: !qstack.qubit):
    qstack.return %q : !qstack.qubit
}

qstack.kernel @prepare_one(%q0: !qstack.qubit)
    allocates 1
    -> !qstack.qubit {
  ^bb0(%q0: !qstack.qubit, %q1: !qstack.qubit):
    %q0a       = cliffords.h %q0
    %q0b, %q1a = cliffords.cx %q0a, %q1
    %m         = qstack.measure %q1a
    %q0out = qstack.select @repeat_until_one(b = %m)
        cases { done = @id, retry = @prepare_one }
        (%q0b) : (!qstack.qubit) -> !qstack.qubit
    qstack.return %q0out : !qstack.qubit
}

qstack.kernel @main()
    allocates 1
    -> !qstack.bit {
  ^bb0(%q0: !qstack.qubit):
    %q0one = qstack.call @prepare_one(%q0)
        : (!qstack.qubit) -> !qstack.qubit
    %result = qstack.measure %q0one
    qstack.return %result : !qstack.bit
}
```

`@main` owns `%q0`; `@prepare_one` owns `%q1`; neither fresh allocation escapes. The selector executes inside the kernel where `%m` is measured. Every possible continuation is a named kernel, so the module is closed for ahead-of-time compilation.

After a repetition-code transformation, physical measurement bits are decoded inside the transformed kernel before the unchanged source selector consumes the logical bit. No function-scope plumbing and no callback wrapper are required.

## 6. MLIR role and deferred work

MLIR remains the substrate for SSA, rewriting, symbol tables, and dialect composition. qstack does not reuse MLIR's function dialect for executable quantum code: the qstack dialect owns its kernel and callback symbols.

This document does not yet fix concrete parser/printer syntax, xDSL class layout, runtime ABI details, verifier implementation, callback-obligation data format, surface-language migration, or noisy semantics. Those follow only after this specification and `verification-design.md` agree.
