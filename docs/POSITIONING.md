# qstack: Positioning

## Elevator pitch

**qstack brings witness-carrying translation validation to quantum compilation.** Each compiler pass produces both a
transformed program and a machine-checkable account of what it changed. An independent verifier checks that witness
locally and composes the results across the pipeline, with the goal of verifying compilation from a high-level hybrid
program through error-correction encoding to machine instructions. No proof assistant is required.

## Why quantum compilation is different

Classical compiler verification provides the model: establish correctness pass by pass rather than trusting the compiler
as a whole. Quantum compilation adds obligations that ordinary circuit equivalence does not cover.

- **Hybrid behavior requires instrument equivalence.** Teleportation and error correction measure qubits during
  execution, process the results, and select later quantum operations. Verification must preserve outcome probabilities,
  conditional quantum states, and interactions with the classical host rather than only a unitary operator.
- **Representation changes require relational checks.** QEC encoding replaces one logical qubit with many physical
  qubits. Verification must relate the logical and encoded states rather than compare two circuits acting on the same
  space.

Verification is necessary because testing provides weak evidence: quantum state spaces are intractably large,
measurement is destructive, and a compiler error can look like ordinary variation in a probabilistic result.

Existing techniques solve important parts of this problem: verified compiler passes, stabilizer verification, and
circuit equivalence checking. qstack puts them behind one witness-carrying translation-validation contract that extends
across hybrid programs and QEC representation changes.

## The contribution

qstack adapts witness-carrying translation validation to the parts of quantum compilation that ordinary circuit
equivalence cannot express. Its design has three parts.

### Witness-carrying translation validation

Every supported pass emits a witness alongside its output. The witness records:

1. the representation relation used by the pass;
2. the rewrite rules it applied; and
3. the source and target regions covered by each rewrite.

The pass is cooperative but untrusted. The verifier checks the rules, checks that each site matches its rule, and checks
that the witness accounts for the complete transformation. A false claim is refuted. A transformation outside the
supported contract is reported as unsupported rather than accepted on trust.

### A hybrid IR with explicit classical boundaries

A qstack program is a closed collection of named kernels rooted at `@main`. A kernel may apply unitaries, measure, call
other kernels, and return classical outcomes or surviving qubits. Qubits and bits are linear, so every value is accounted
for.

Classical computation sits behind two explicit callbacks: a decoder maps measurement bits to one bit, and a selector
chooses from a finite set of named kernels. Callback implementations remain opaque to the compiler. Existing callbacks
are preserved exactly, including their inputs and global invocation order.

This keeps measurement and feedback in place instead of converting the program into a pure unitary circuit. The
verifier can inspect every quantum continuation without inspecting arbitrary host-language code.

### Representation-changing verification

All passes have one top-level obligation: preserve program behavior through a declared representation relation.
Optimizations and ordinary gate lowerings use the identity relation. A QEC pass instead declares an encoding `V` from a
source qubit to an encoded block.

For a unitary rewrite, the verifier checks the corresponding logical-action equation:

```text
U_target V = V U_source
```

It also checks that allocation prepares the encoded source state and that each encoded-measurement rewrite recovers the
source observable. This is how qstack crosses the QEC boundary without pretending that the source and target operate on
the same qubits.

## One contract, multiple verification methods

The pass contract defines what must be shown, not how to show it. Small rules may use dense matrices, Clifford rules may
use stabilizer methods, and larger supported rules may use an external equivalence checker. A backend can verify, refute,
or decline a rule.

| Transformation | Typical obligation |
| --- | --- |
| Gate decomposition or exact synthesis | Equality of small unitaries |
| QEC encoding | Encoding, logical-action, measurement, and decoding rules |
| Layout and routing | Equivalence of witnessed routing rewrites |
| Optimization | Equivalence of witnessed local rewrites |

This is the intended meaning of method-agnostic: new sound backends can be added without changing the compiler contract.
It does not mean that every backend handles every pass, or that every possible transformation is supported.

Most semantic work is performed once per distinct rewrite rule. Its applications are then checked structurally. The cost
therefore follows the number and width of rules more closely than the state space of the complete program, while failures
remain attributable to a particular rule or site.

## Classical obligations

A pass may introduce a decoder or selector as part of a verified quantum rewrite. qstack derives the finite behavior
that callback must implement and reports it as a classical obligation; it does not trust the implementation implicitly.
Existing callbacks, by contrast, pass through compilation unchanged.

The result is either verified, verified modulo explicit classical obligations, refuted, or unsupported. Once the
classical obligations are discharged, the compiled program preserves returned results, conditional quantum states, and
all pre-existing host interactions through the declared representation relation.

## Guarantee boundary

qstack's first guarantee is **noiseless semantic preservation**. It establishes that compilation preserves the ideal
computation, including across QEC encoding and hybrid measurement-feedback boundaries. It does not by itself establish
code distance, fault tolerance, a threshold, or correct execution under a noise model.

Those are future layers of the full-stack goal. Approximate synthesis likewise requires an approximation relation and a
composable error budget beyond exact equivalence. Keeping these boundaries explicit lets later guarantees build on a
precise compiler-correctness foundation.

Validated translations compose: if each pass preserves its input through its declared relation and all classical
obligations are discharged, the pipeline preserves the source program through the complete sequence of representations.
qstack's goal is to carry that guarantee from a high-level hybrid program through QEC encoding to machine instructions.
