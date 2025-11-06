We thank the reviewers for their thoughtful feedback, which will improve our work going forward.

We agree with the reviewers that the novelty here is largely the integrated classical-callback mechanism that works in a stack-like fashion. We believe this novel design choice is significant for the expression and compilation of quantum algorithms and error correction. This is a matter of design – there's no fundamental increase in expressive power over existing approaches or systems, just as a stack-based virtual machine has no expressive power over assembly language.

Another main contribution is that our approach allows us to treat quantum error correction as a compilation step (as opposed to something you inject at runtime) that can be applied to any existing program. The compiled result maintains the same programming model and can be further compiled with additional error correction layers, enabling automatic code concatenation. This is necessary due to the nature of QEC vs classical ECC: classical error correction only needs to worry about memory, while QEC is actively applied during computation by performing computations on encoded qubits.


# Reviewer A 

## Main Issues

* A heap with named references for qubits would be a poor fit for compilation to quantum hardware – qubits are much more like registers than memory locations, and the stack approach, where the address of qubits cannot be taken, allows straightforward compilation until "stack overflow" occurs when the machine lacks sufficient qubits. This is indeed a question of design – a stack represents a middle ground between statically allocated registers and a heap with addresses and aliasing. In our view, the quantum programming literature has focused mostly on the register space, and we advocate for the stack space rather than the heap space. The literature would be enriched by research across all these dimensions.

* The stack discipline fits well with modular composition and translation – compiler passes for tasks like error correction can work "in place" at a position in the stack.

* We agree our approach could, with some effort, be implemented on top of Qiskit. We are not trying to replace Qiskit with our prototype but rather demonstrate the value of qstack's design. Our backend uses the full state simulator from Q#, but retargeting to Qiskit would not provide additional insights. Our comparison shows that one cannot easily follow our methodology in Qiskit due to the awkward support for classical computation.

* We agree that our model assumes mid-circuit measurement "works" without latency concerns and that this has practical limitations, but we believe there is still value in generalizing the concept of mid-circuit measurement as a classical callback.

## Details

Line 642: Yes, thank you.

# Reviewer B

## Main Issues

* Regarding the "fundamentally the wrong design decision" – We respectfully disagree. We are fundamentally an embedded DSL, which is not only a common, powerful paradigm, but one widely used in quantum programming (e.g., Qiskit, Cirq, Quipper, etc.). The use of strings is entirely optional (and indeed, often not advised) – we have constructors just like in EDSLs, but do sometimes use strings/parsing for concision and readability; the use of strings is absolutely not fundamental to our approach. Having callbacks generate the next kernel does indeed trade off flexibility for the ability to analyze statically what quantum code might next run, but the entire purpose of partial measurement is to use partial observations to control what quantum code is run next – making these control decisions in Python (any classical language is fine) is convenient, and when the decisions are simple, static analysis would remain feasible. Alternating classical and quantum execution in a structured way makes a number of algorithms in the space simpler by separating the classical from the quantum. Future work could explore how beneficial it is to restrict the classical side in the interest of static analysis.

* Regarding "code duplication" – No duplication is necessary. The example on page 3 duplicated the code for exposition, but the footnote on page 3 explains exactly how to avoid this duplication.

* Regarding "performance bottleneck" – Millions of wasted classical computing cycles in the context of controlling a computation on a quantum computer is not an issue for algorithms that make sense to use quantum for, given the scale of classical overhead compared to quantum operation times.

* Regarding "complicates the operational semantics" – Because the purpose of the callback is to determine the next quantum computation, returning that computation is directly what is needed here – it's unclear what would be simpler. This approach is common in EDSLs. Continuation-passing style is, in our view, essentially the same thing: you could take our stack-based language, apply the CPS-transform to it, and, as always, have an identical program. But why program in that style for the sorts of algorithms we aim to express?

* Regarding "typos in the semantic rules / correctness" – there is one trivial typo Reviewer A also found (the 'q' on line 642 should be 'q_k') along with writing :== when we should have written ::=; the other issues listed below are not correct. Please see details below.

* Regarding "lack of value of the operational semantics" – our goal was to make the semantics of qstack fully precise. We agree that if someone wished to prove a translation from qstack to some other language or approach, then the operational semantics would be the foundation for that.

* Regarding "qualitative evaluation" – we agree this is a challenging area: There are no established benchmarks and our focus is on language design. We did our best to elucidate how implementing similar programs in Qiskit, as a current leading example in the area, is more challenging without the callbacks and stack-based discipline, but it is unclear what objective or quantitative metrics would be convincing for this kind of work.

## Details

* 113: "Justify the choice of Python" - We chose Python for its widespread adoption in quantum computing research, making our framework accessible to the intended audience. However, our approach is language-agnostic – any classical language could host the callbacks since we treat classical components as opaque. Nothing Python-specific is relevant.

* 222: "serious instruction set" - A core advantage of our approach is its ability to work with diverse quantum instruction sets at different abstraction levels, which is why we focused on demonstrating this flexibility rather than providing a single "serious" instruction set. Section 3 explicitly describes a canonical instruction set (Pauli gates, Hadamard, CNOT, etc.) and shows how our framework handles compilation between toy, canonical, and hardware-specific instruction sets like Quantinuum's trapped-ion gates.

* 228: "dynamic program structure" - We use "dynamic" to refer to two aspects of our framework: dynamic qubit allocation (qubits are allocated and deallocated during program execution rather than pre-allocated) and dynamic program structure (callbacks can return new kernels, allowing the program's control flow to change based on measurement outcomes at runtime).

* 257-291 and 329-330: "wrong that callbacks always take one argument" – We disagree but this is perhaps a matter of taste. We drew inspiration from languages such as OCaml and Haskell where all functions take exactly one argument and other argument counts are easily supported via programming patterns (currying) and syntactic sugar. These are all well-known trade-offs. An alternate formulation where each kernel can introduce any number of qubits would also be fine. We don't see anything deep here.

* 319 "prepare_magic_state": The prepare_magic_state operation creates a specially prepared quantum state needed for T-gate injection, as described in the preceding paragraph. This is a standard technique in fault-tolerant quantum computing where T-gates are implemented indirectly through magic state distillation rather than direct application.

* 330: "s and target_qubit" – Thank you. We omitted the definition of the s gate (will fix) and target_qubit should be target (will fix).

* 370: "something is wrong with a compiler if the order of all phases can be switched" - We should clarify that compilation phases can typically be switched when the input and output instruction sets are the same—a common scenario in quantum error correction where transformations add redundancy without changing the underlying gate set. However, when compilation involves instruction set translation (e.g., from canonical gates to hardware-specific gates), phase ordering becomes significant and cannot be arbitrarily reordered. Most compilers work this way as well: lowering stages happen in a fixed order while optimization phases at a level can be arbitrarily composed and reordered.

* 373-374 "eval() is evil": This perspective is usually attributed to within a language, like Javascript's eval generating Javascript. For an embedded DSL, the entire approach is that the host language uses data structures to create DSL programs and that is what we do, though we do provide, if desired, parsing functions that allow the use of strings to create the data structures. It is true that in principle any quantum program, even ill-formed ones, could be created at runtime, leading to runtime errors or nonsensical programs. In that sense the embedded DSL approach is "too powerful", but (a) this is not the hard part of quantum programming and (b) this same criticism holds of many well-recognized quantum languages that take the same approach (e.g., Qiskit, Cirq, Quipper, etc.).

* 413-414: "what is the canonical instruction set?": It is defined a couple of paragraphs above: "quantum programs are typically expressed in terms of a canonical instruction set consisting of commonly used quantum gates with standardized names. These gates, also called quantum instructions, are unitary operations that transform quantum states while preserving quantum properties like superposition and entanglement. The canonical set usually includes Clifford operations --- the Pauli gates (X, Y, Z), Hadamard (H), phase (S), and controlled-X (CX)—along with arbitrary single- or two-qubit rotations."

* 478-490: We disagree that a compiler phase would "have trouble" getting any of this right. It creates the nested kernels to perform a transformation like error correction and inserts the callbacks that do the measurements to perform error detection/correction. Compiling into a stack-based discipline is extremely common (e.g., Java local variables and nested expressions compiled to JVML).

* 589-595:
  * Yes, :== should be ::=, a trivial metasyntactic error on our part
  * Kernels do use a new more concise syntax, but we thought it was clear that this contains a name for the allocated qubit, a list of instructions, and a callback, as defined with later productions
  * Kernels are indeed a form of instruction and this seems fine – we don't see an issue with the word 'instruction' for a recursive definition, though we can replace the name if helpful
  * Gates, as in many prior descriptions of quantum programming, take one or more qubits and apply a unitary matrix to them, updating the quantum state. It would not make sense for a gate to take zero arguments – the unitary would be of size 0x0 and have no effect.

* 599: The fixed mapping corresponds with our view that each instruction set would have a fixed set of instructions, but we agree this could be generalized and made more flexible.

* 623-625: While any execution starting from an initially empty quantum state would have the size of the state vector and the qubit name map related, this relation does not need to be defined for the rules to be valid.

* 627: S_0 is whatever initial classical state exists – no rules depend on it. Think of it as the formalization of what classical code produces before quantum execution begins.

* 642: Agreed; thank you.

* 654: Gates operate on quantum states and may need multiple qubits. Callbacks receive the measurement of a qubit – they are not similar or interchangeable in any way, so we don't see any reason they'd have similar arity. But as discussed above, some languages have multiargument functions and some don't – both ways work fine.

* 662-665 and 673-676: These rules are correct. The hypothesis m = m' ⊎ [q ↦ n-1] means m must be the disjoint union of some m' and [q ↦ n-1] – it's a pattern match deconstructing m that will apply only when m contains the mapping q ↦ n-1. We could have instead written m' ⊎ [q ↦ n-1] in the conclusion of the rule where m appears, but found this a bit less readable. The two approaches have the same well-defined meaning.

* 736-745: Multiple allocates and one measure was explained on page 6 but could be re-explained here. The "qubit=q1" is indeed an infelicity that should have been elided – our minor error.

* 777: "+1 eigenspace unexplained jargon" - We aimed to make the document self-contained for quantum computing concepts, but assumed familiarity with standard linear algebra terminology like eigenvectors and eigenspaces. Since we already explained that valid encoded states are +1 eigenstates of every stabilizer, the '+1 eigenspace' simply refers to the collection of all such valid states.

* 789: "syndrome_table undefined" - The syndrome_table is described in Figure 3's caption as a lookup table that maps syndrome patterns to error locations. While we could provide the complete table, this is a standard component of Steane code implementations and the decode function clearly shows how it's used to identify and correct errors.

# Reviewer C 

## Main Issues

We can work on improving the first page, though it can be difficult in a self-contained paper to get to the substance before 1.2.

The slightly different syntax for the formalism is perhaps a matter of taste – we thought kernels of the form q : instructions : cb would be parsimonious here but could change them. As usual for formal semantics, our goal was to formalize only non-sugared programs.

We agree the stack-based discipline could, in theory, be an issue when you want to measure in a different order than you allocate. Across a range of examples, we have not seen this. Similar issues arise in any stack-based discipline yet stacks are incredibly common for memory allocation/deallocation. The only issue we can really see is when one measurement affects the order of future measurements, as then you can't know at allocation time what order to use. We have not found an algorithm with this behavior. But if one arises, the LIFO measurement constraint doesn't reduce expressive power since any qubit can be moved to the top of the stack using SWAP gates (standard unitary operations) or quantum teleportation protocols.

On novelty: We fully agree – the callback wrapping is the main interesting idea. We did not mean to underplay this. The surrounding 'routine material' is to show that this interesting idea works with all the other components that are still needed.

We agree the code in the Steane section reads like a standard implementation, but that's a feature from our point of view. Our main contribution is to demonstrate how it (and more broadly error correction codes in general) can be transparently injected as a compilation step into any existing program. The compiled result maintains the same programming model and can be further compiled with additional error correction layers, enabling automatic code concatenation. We can better emphasize this compositional aspect over the implementation details. We also agree the earlier repetition code demonstrates all this as well, but because a repetition code is not useful in practice, we felt it was important to teach the concepts with a simple code but also demonstrate the concepts work with a useful code.

## Details

(See above which also answers the 'specific questions')
