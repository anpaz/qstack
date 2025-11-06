
### Languages and Intermediate Represenations

#### Quipper (https://arxiv.org/pdf/1304.3390):

Quipper is one of the first quantum programming languages designed to let developers express quantum algorithms in a **high-level, declarative style**. Implemented as an **embedded domain-specific language (DSL)** within Haskell, Quipper leverages Haskell’s type system and higher-order functions to construct and manipulate quantum circuits programmatically. Its simplicity is reflected in a small set of fundamental data types: a *classical bit*, a *quantum bit*, a *gate*, a *box* (representing reusable subcircuits), and the *Circ* monad, which provides the computational context for circuit construction.

At its core, Quipper exposes a single control structure for conditional operations—the `controlled` keyword. This construct specifies whether a gate should be applied depending on a control bit. If the control bit is *quantum*, the statement produces a **quantum-controlled gate** that is always part of the circuit; if the control bit is *classical*, the gate is included only when the bit’s value equals one. The distinction ensures that the resulting circuit preserves unitarity where appropriate while still allowing classical control flow.

Developers write Quipper programs using the full expressive power of Haskell, but rather than executing quantum effects directly, they *generate a circuit* within the `Circ` monad. Executing a Quipper program thus proceeds in three stages:

1. **Compilation**, where the Haskell compiler builds the Quipper program itself.
2. **Evaluation**, which runs the Haskell code to *generate* a quantum circuit representation.
3. **Execution**, where the produced circuit is sent to a quantum backend or simulator for actual computation.

Quipper also supports **mid-circuit evaluation** through a feature known as *dynamic lifting*. This mechanism allows the program to pause circuit generation upon a measurement, perform classical computation on the measurement outcomes, and then resume circuit construction based on those results—enabling hybrid classical–quantum control flow within a single program.

Internally, the generated quantum circuit is represented as a **directed acyclic graph (DAG)** of gates. Each gate is defined by its name, control and target wires, inversion flag, and optional annotation:

```haskell
data Gate = Gate { gate_name  :: String,
                   controls   :: [Wire],
                   targets    :: [Wire],
                   inversion  :: Bool,
                   annotation :: Maybe Annotation }
```

This structured representation can be serialized into various formats—including OpenQASM, Quipper’s own ASCII format, and Graphviz—for analysis, visualization, or hardware execution. Together, these design choices make Quipper one of the earliest and most influential efforts to bridge the gap between functional programming abstractions and practical, large-scale quantum circuit design.

#### Q# https://arxiv.org/pdf/1803.00652 and QIR (https://github.com/qir-alliance/qir-spec)

Q# was introduced by Microsoft Research in 2018 as one of the first **stand-alone, purpose-built, high-level quantum programming languages** (Svore et al., 2018). Unlike earlier frameworks embedded in host languages, Q# was explicitly conceived as a *compiled language for quantum algorithm design*, not just circuit construction. It enforces a clear separation between classical and quantum computation, provides strong static typing, and supports automatic uncomputation.

The language adopts a familiar C-style syntax (`if`, `for`, `while`, `{}` blocks) but introduces a rich type system that distinguishes classical and quantum entities. Programs are structured around two kinds of callables:

* **Functions**, which are purely classical and side-effect-free, evaluated entirely on the host CPU.
* **Operations**, which describe quantum subroutines that allocate, transform, and measure qubits.

Primitive types include `Bool`, `Int`, `Double`, `String`, `Result`, and `Qubit`; composite types (tuples, arrays, and user-defined records) enable structured data. The type checker enforces separation between quantum and classical data to avoid nonsensical operations, such as comparing qubits or printing them directly.

Q# introduced several innovations that shaped later language designs:

* **Functor semantics:** operations can automatically derive *adjoint* and *controlled* versions, ensuring unitarity and composability without manually constructing inverse circuits.
* **Scoped qubit management:** `using` allocates qubits initialized to |0⟩, and `borrowing` temporarily reuses ancillas assumed to be in |0⟩, providing lifetime safety and enabling qubit recycling.
* **Structured uncomputation:** the `within`/`apply` construct formalizes the common “compute–use–uncompute” pattern, guaranteeing cleanup of temporary entanglement.
* **Type-safe composition:** the distinction between classical functions and quantum operations is statically enforced, preventing cross-domain side effects.

These features make Q# the first *industrial-grade, standalone, compiled* quantum language that can express complete algorithms—from oracle definitions to amplitude amplification—without manual circuit management.

***QIR — Quantum Intermediate Representation***

To bridge high-level Q# semantics and hardware execution, Microsoft and partners developed **QIR (Quantum Intermediate Representation)**, a hardware-agnostic IR embedded in LLVM. QIR defines a canonical interface between quantum programs and backends, representing quantum instructions as calls to standardized functions such as `__quantum__qis__h`, `__quantum__qis__cnot`, or `__quantum__qis__measure`. Quantum data is represented as opaque pointers (e.g., `%Qubit*`, `%Result*`), while classical control uses standard LLVM constructs.

For example, a simple Bell-pair creation operation might lower to:

```llvm
define void @CreateBellPair__body(%Qubit* %q1, %Qubit* %q2) {
entry:
  call void @__quantum__qis__h(%Qubit* %q1)
  call void @__quantum__qis__cnot(%Qubit* %q1, %Qubit* %q2)
  ret void
}
```

The QIR specification defines **profiles** that constrain the allowed interaction between classical and quantum instructions:

* The **basic profile** disallows all runtime classical expressions, yielding a static sequence of quantum instructions. Classical loops and branches are resolved by the compiler (e.g., loop unrolling and constant folding), producing a flattened circuit representation.
* The **adaptive profile** permits limited classical computation—such as branching on measurement results—to support dynamic control and hybrid algorithms.
* Additional profiles may target device-specific features or richer hybrid control, while preserving the same LLVM substrate.

By embedding quantum constructs directly into LLVM, QIR inherits its optimization infrastructure and well-defined semantics, enabling quantum programs to coexist with classical code and pass through standard compiler pipelines. The combination of **Q#** and **QIR** thus establishes a clean division of concerns: Q# serves as the algorithmic front-end with strong semantics and safety guarantees, while QIR provides a portable, backend-neutral representation for execution and optimization across diverse hardware targets.



#### Silq (https://files.sri.inf.ethz.ch/website/papers/pldi20-silq.pdf)

Silq is a high-level quantum language that tackles a major usability issues in quantum programming: manual uncomputation. Traditional frameworks like Quipper require programmers to explicitly uncompute temporary data to keep circuits reversible and ancillae clean. Silq automates this through a type system that infers when an expression is quantum-free (qfree)—that is, a classically describable, bijective transformation over basis states—and automatically inserts the inverse of that transformation when the temporary result is discarded. Qfree computations can be interpreted as lifted classical permutations over “ground sets,” ensuring that automatic uncomputation is sound without tracking amplitudes or entanglement.

This mechanism enables high-level quantum control structures. For example, checking whether an n-bit register equals a constant requires flipping the zero bits of the constant’s binary representation, performing a multi-bit AND to compute a flag, and then unflipping the bits to restore the original register. In Silq, those scaffolding operations are qfree, so the compiler can automatically uncompute them once the comparison is complete. This makes it possible to write an if expression that can test not only single qubits (as in controlled gates) but also entire integer registers or structured data.

Silq unifies classical and quantum control through types: a value annotated as `!N` is classical and can be copied or discarded, while an unannotated N may hold a superposition. This distinction determines whether a control structure is executed classically or coherently. However, since current quantum hardware cannot yet realize full quantum control, developers must still reason about which if expressions should be classical and which can safely remain quantum. The resulting notation is expressive but subtle: the same syntax may denote entirely different operational behaviors depending on type inference and compiler reasoning.

Silq reminds me of Perl: it allows remarkably concise, high-level expressions that hide deep operational complexity. When the program is fresh in mind, the code feels elegant and minimal; months later, it can be opaque without re-deriving the compiler’s inference of what is classical, what is quantum, and what was uncomputed. The PLDI paper remains theoretical—no hardware-specific lowering or IR mapping is described—and the set of qfree primitives is fixed rather than user-extensible. Still, Silq stands out as the first serious attempt to make reversibility a semantic property of a high-level language rather than an explicit programming discipline, bridging classical and quantum control structures within a single type framework.

----

#### Qunity (https://arxiv.org/pdf/2508.02857)

**Qunity** is a high-level quantum programming language that challenges the traditional *QRAM model*—where a classical processor drives execution and a quantum device merely acts as a passive coprocessor—by giving **quantum control flow** first-class status. Its core goal is to unify classical and quantum control within a single, compositional semantics.

At its foundation, Qunity defines a **minimal core calculus** built from a handful of data types and operators:
* **Types:** `Unit`, products (`⊗`), sums (`⊕`), and derived algebraic types built from them.
* **Core instructions:** `left` / `right` injections (for sums), tensor pairing, `case` expressions (pattern matching), composition, and basic unitaries / isometries.

This core fragment is mathematically elegant: every well-typed program corresponds to a **linear operator** between Hilbert spaces (H(T) → H(T')). Products (`⊗`) denote coexistence (“and”), while sums (`⊕`) denote alternatives (“either/or”), realized physically as **orthogonal subspaces** separated by a *flag qubit*. Control flow constructs compile into **block-diagonal operators** (E_0 ⊕ E_1), which apply different unitaries on each branch but preserve global coherence—essentially generalizing “controlled operations” to arbitrary datatypes.
It provides one of the most complete and compositional formal accounts of **quantum control flow**, grounded in the algebraic structures of Hilbert spaces (⊗ for conjunction, ⊕ for disjunction). The work exposes how deeply difficult it is to “marry” classical and quantum execution in a single semantics:
* Classical control wants branching, duplication, and termination.
* Quantum control demands linearity, reversibility, and coherence.
Qunity’s type system and semantics show precisely how these worlds can coexist—at the cost of considerable syntactic and conceptual complexity.

**Type System and Classical–Quantum Boundary**
Qunity enforces a **sophisticated type system** that distinguishes between classical and quantum data, ensuring linearity, orthogonality, and encoding validity.
* Classical data can be copied, discarded, or used in ordinary control.
* Quantum data cannot be duplicated or erased, so its control structures must be linear (coherent).
This system allows the compiler to statically determine where operations remain reversible and where measurement (and therefore classical control) is required.
However, this typing discipline leaks into syntax. The programmer must still choose between variants such as `match` (classical), `pmatch` (quantum/coherent), and `ematch` (effectful with measurement). This explicit distinction preserves soundness but makes programs more verbose and sometimes harder to read—one of the main usability tensions of the design.

**Surface Syntax and Meta-Language**
Because the core calculus is too austere for real programming, the paper extends it with a **surface syntax**—a richer, *meta-language* that adds:
* Recursion and higher-order functions (evaluated at compile time, not quantum runtime),
* Parametric and user-defined datatypes,
* More expressive pattern matching (`pmatch`, `ematch`, etc.),
* Syntactic sugar for tensor composition, subroutines, and “classical-then-quantum” sequencing.
This meta-language is evaluated **classically**; it *generates* a finite Qunity core term, ensuring that the compiled circuit remains linear and unitary.
In that sense, recursion and looping exist only as *compile-time metaprogramming tools*, not as runtime operations over live quantum states.

**Why Recursion Fails in Pure Quantum Semantics**
It is interesting to emphasize that pure quantum (linear) languages disallow unrestricted recursion for deep reasons:
1. **Unitarity:** Quantum evolution must be reversible and finite-dimensional. A recursive function implies potentially unbounded iteration—something no finite matrix can represent.
2. **No-cloning / No-deletion:** Recursive calls would require duplicating or discarding quantum data, which violates linear typing.
3. **Termination:** A total linear map must be defined everywhere and terminate in finite steps; recursion breaks that guarantee.
Thus, the Qunity core intentionally forbids general recursion, ensuring that every program denotes a finite linear operator. The surface meta-language sidesteps this by performing recursion *before* code generation, expanding into a finite circuit.

**Compilation**
The Qunity compiler translates high-level programs—full of quantum control, algebraic data types, and compositional operators—into plain circuits by progressively lowering them through a typed, linear intermediate form. Each program is first desugared into a **core operator DAG**, whose nodes represent Hilbert-space operators (tensor, sum, injection, case, composition) and whose edges carry encoded qubit registers. Every type is then mapped to a concrete bit-level encoding: products concatenate registers, while sum types introduce a **flag qubit** separating orthogonal subspaces. This structured representation, though mathematically elegant, is straightforward to traverse: the compiler simply expands it into a sequence of controlled and parallel unitary blocks.
In the final stage, Qunity emits **OpenQASM 3**. All the high-level quantum control constructs—`pmatch`, `ematch`, and block-diagonal operators—compile down to familiar OpenQASM-style primitives: controlled gates, classical `if`/`while` branches, and measurement instructions. Despite Qunity’s unified treatment of classical and quantum control in its semantics, the end result is a standard circuit in OpenQASM 3, ready to run on any compatible backend. The elegance is in the path, not the destination: no matter how abstract the control structures, everything ultimately compiles into an ordinary gate-level description.


#### OpenQASM 3 (https://dl.acm.org/doi/pdf/10.1145/3505636)

OpenQASM 3 (Cross et al., 2022) is a *low-level assembly language for quantum programs*, designed as a **machine-independent intermediate representation (IR)** bridging high-level quantum languages and hardware-specific backends. Originally created as a minimal gate-level format (OpenQASM 2), it has evolved into the *de facto* standard for low-level circuit representation across toolchains such as Qiskit, Braket, and Cirq. Its primary goal is to describe complete **hybrid quantum–classical** experiments while remaining agnostic to device technology—superconducting transmons, trapped ions, neutral atoms, photons, or Majoranas—so that compilers and schedulers can later specialize programs for a given target.

At its conceptual core, OpenQASM 3 treats a quantum circuit as a **computational routing**: an ordered sequence of quantum operations (gates, measurements, resets) on quantum data, optionally interleaved with real-time classical instructions. The language distinguishes **real-time control**, which must execute within the coherence window of the qubits, from **near-time control**, which can be performed asynchronously by a host processor. Real-time computation allows direct feedback such as

```qasm
if (c == 1) x q;
```

while near-time computation is enabled through the `extern` keyword, which declares a host-side function returning a classical result later consumed in the circuit. This separation mirrors hardware reality: fast, low-latency loops are expressed natively in OpenQASM 3, while slower coordination tasks occur off-chip.

**Language Constructs and Storage Classes**
OpenQASM 3 introduces a structured, lexically scoped, *declarative* syntax that unifies quantum and classical operations within one language. Variables are explicitly declared and scoped, each belonging to a **storage class** rather than a type hierarchy. The supported kinds are:

* `qubit` and arrays thereof (quantum storage),
* `bit` (classical single-bit result registers),
* numeric and logical storage forms: `bool`, `int`, `float`, `angle`,
  and arrays of fixed size.

Variables may be declared as mutable (`let`) or constant (`const`), and expressions combine arithmetic, logical, and bitwise operations over these storages. There is no dynamic typing or runtime dispatch; the syntax enforces consistency by construction. Control flow follows an imperative block structure with `if` / `else`, `for`, and `while` loops, plus `break` / `continue` for structured exits. Subroutines defined via `def` can describe both classical computations and quantum gates with parameter lists and local scopes. There are no recursive calls or dynamic allocation—every program is finite and statically analyzable.

**Instruction Layers and Circuit Semantics**
The instruction set divides into three conceptual layers:

1. **Logical-Circuit Layer.** Describes the standard circuit model: a sequence of unitary and non-unitary operations on qubits. OpenQASM 3 defines a single universal gate primitive `U(θ, φ, λ)` from which all other single-qubit gates derive. Composite gates can be declared from sequences of other gates, and the language includes a built-in library of standard operations (`x`, `h`, `cx`, `rz`, etc.). Version 3 introduces **gate modifiers**—`ctrl`, `inv`, and `pow`—to generate controlled, adjoint, or fractional variants. Measurements and resets are treated as first-class, non-unitary operations integrated into the same flow.

2. **Classical-Instruction Layer.** Provides the minimal classical substrate for real-time feedback: arithmetic and boolean expressions, explicit loops and conditionals, and callable subroutines. Together these instructions allow classical computation tightly interleaved with quantum operations, permitting immediate control decisions based on measurement outcomes.

3. **Physical-Circuit Layer.** Extends the language to **pulse-level** and **timing-aware** control using primitives such as `delay`, `stretch`, and waveform specifications. These constructs permit calibration routines and precise temporal alignment within the same syntax, bridging OpenQASM and OpenPulse.

Features such as memory management, recursion, or unstructured `goto`-style jumps were deliberately excluded to keep the representation static, schedulable, and verifiable by downstream compiler passes.

**Compiler IR**
OpenQASM 3 explicitly targets use as a **compiler IR**—a structured but low-level language suitable for passes such as circuit layout, routing, timing analysis, and optimization before translation to pulse-level control. It defines a well-formed, hardware-neutral syntax that can represent both unitary and measurement-driven control, ensuring portability across architectures. Despite its assembly-like appearance, its execution model is richer than simple circuit playback: an OpenQASM 3 program is effectively a *hybrid dataflow graph* of quantum and classical operations evolving in real time. As a result, nearly all major quantum software stacks compile to or interoperate through OpenQASM 3, making it the canonical bridge between high-level quantum languages (Q#, Silq, Qunity, Quipper) and hardware backends.


#### Stim (https://arxiv.org/pdf/2103.02202)

**Stim** is a high-performance simulator for *stabilizer circuits* (circuits composed of Clifford operations, measurements, and classically controlled Pauli corrections). Such circuits form the backbone of most QEC schemes, since stabilizer measurements, syndrome extraction, and Pauli-frame updates can all be expressed within this restricted fragment. Although stabilizer circuits are not computationally universal, they can be made so by adding non-Clifford gates (such as *T* gates) through magic-state injection. Crucially, their evolution can be simulated efficiently on classical hardware using tableau representations of the underlying stabilizer group. This property allows Stim to model large-scale QEC circuits with exceptional performance: for example, preparing a circuit with 20 000 qubits, 8 million gates, and 1 million measurements in under fifteen seconds, and sampling measurement outcomes at rates exceeding one kilohertz. As a result, Stim has become the de facto standard simulator for QEC research and development.

At its core, Stim represents circuits using a compact assembly-style language designed for speed and clarity. Each line corresponds to an instruction (typically a Clifford gate, measurement, reset, or classically controlled operation) followed by its target qubits. The syntax is intentionally minimal: integers label qubits, and measured results can be referenced through `rec[-k]` indices, which refer to the *k-th most recent measurement result* in the circuit. This mechanism provides the means for classical feedback: a Pauli operation can be conditionally applied based on previous measurement outcomes. For example, `CX rec[-1] 5` applies an `X` gate on qubit 5 only if the most recent measurement yielded 1. Similarly, per-shot configuration bits can be specified with `sweep[i]`, enabling deterministic control of circuit variants across simulation runs. Stim restricts this feedback to single-control Pauli operations (multi-control logic or non-Pauli feedback is not supported in the textual format, although more complex behavior can be expressed through its Python API).

Beyond the basic gate set, the language includes several auxiliary constructs to aid circuit organization and analysis. The `REPEAT N { ... }` block efficiently defines identical circuit rounds, heavily used in QEC cycles. `TICK` statements mark logical time steps, allowing operations to be grouped into synchronous layers. `DETECTOR` and `OBSERVABLE_INCLUDE` instructions identify stabilizer checks and logical observables without affecting circuit execution, enabling automatic generation of detector-error models for decoders. Optional noise channels such as `X_ERROR(p)` and `DEPOLARIZE1(p)` inject Pauli stochastic errors immediately after the preceding operations, without leaving the stabilizer formalism. 


