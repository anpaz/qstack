
## Introduction

- Quantum programs are complicated.
  * They leverage quantum mechanics phenomena to perform efficient calculations.
  * Hard to debug:
    - instructions update complex probabilities
    - instructions modify all possible outcomes simultaneously
    - can't peak at the state without collapsing
  * Hard to test:
    - most don't have deterministic outcomes, so it can take millions of shots to get statistical certainty of probabilities distributions
    - without deterministic outcomes typical testing techniques of picking a few inputs and evaluate them don't work. Makes verification and proving even more critical than in classical programs.
- Quantum hardware is complicated.
  * As opposed to classical system, in which all computers uses transistors, there are many different technologies that can realize a quantum computer (Ions, Superconductor, Neutral Atoms, Photons, Majoranas)
  * Each of these have a different set of universal gates
  * Writing software targeting each of these platforms would be super complicated, instead we do similar to what we do in classical: have a layer of abstraction that enables to write applications on a canonical set of gates or instructions, which can then be compiled into gates targeting different machines
- Quantum hardware is noisy.
  * Quantum devices typically need to be able to manipulate atomical level particles.
  * Not only this is hard, but it tends to make devices faulty, aka noisy
  * Mathematically, noisy means that instead of performing the expected operation the computer will randomly do something else, will introduce a fault.
  * Makes debugging even harder: is the random outcome consistent with the expected outcomes distribution, or is it due to noise. 
  * The good news is that there are quantum error correction techniques that can reduce the probability of a fault.
- Multiple layers of abstraction
  * We model error correction as another hardware abstraction:  just as canonical instruction sets hide physical gate implementations, error correction codes hide the complexities of encoding, syndrome detection, and correction protocols. 
  * On an quantum error correction code both the qubits and instructions need encoding. Information on each qubit is encoded into multiple qubits using entanglement to create resilience. Instructions typically require complex sub-circuits to apply the same logical effect on the corresponding encoded qubits.
  * From the programmer's perspective, a logical qubit and instruction protected by an error correction code behaves closer to an ideal physical qubit and instruction, despite requiring hundreds of physical qubits and sophisticated classical control systems for its implementation. 
  * Other hard problems of quantum programming are abstracted/ignored and expected to be implemented as compiler passes. Some of them, like scheduling, synthesis and optimizations, are their own area of research and as such they tend to be complicated and hard to implement, making them error prone:
    - Layout and Scheduling: to entangle two qubits, the hardware requires that there exist a physical connection between qubits, but in certain technologies the connectivity between qubits is typically limited, as such a compiler pass must decide what is the most effective way to lay qubits on a lattice in a way that minimize their movement and maximize their connectivity to related qubits.
    - Synthesis: Synthesis is the compiler’s task of mapping a high-level quantum operation into a finite sequence of the target hardware’s primitive gates. A gate set is considered universal when it can approximate any quantum operation to within an arbitrary small error. For example, the Clifford+T set together with CNOT is approximately universal. In particular, any single-qubit rotation can be approximated to a desired precision by a finite sequence of H and T gates. Exact synthesis is only possible for a discrete subset of rotation angles; otherwise, the compiler produces an approximate implementation.
    - Optimizations: Things like cancel self-adjoint operations.
    - Qubit reuse: implement dynamic memory and reuse qubits when allocating qubits that are not in used anymore.
  * These abstractions help breaking implementation of quantum programs into smaller, constrained problems, and it creates a multi-layered abstraction hierarchy where canonical instructions may target either physical qubits directly or logical qubits protected by error correction, where qubits might freely perform multi-qubit instructions with any other qubits but in which all abstractions ultimately lowered to the primitive gates and the constraints supported by physical hardware.
- Hybridness
  * Typically overlooked is the fact that very few interesting algorithms can be implemented using only pure quantum instructions.
  * As with classical computer, power comes from the fact that you have control structures that can decide what instruction to run next.
  * Even core basic algorithms like Teleport depend on this. 
  * Even more obvious when using quantum error correction protocols with real-time corrections.
  * How do you design languages for quantum programs that require arbitrary classical logic for their control? How can you verify them?
- Compilers
  * Compilers play a critical role in the quantum software stack bridging the different layers of abstraction
  * They can be difficult to write and difficult to test since, as we described, resultings programs are hard to test.
  * Many compiler passes are more than just simple optimizations or 1-1 gate transformations. Scheduling, Layout, Synthesis can drastically change the contents of the program.
  * TODO: apply similar ideas are those in the introduction of the Giallar paper:
    - Compiler bugs can introduce bugs that can be easily confused with noise on the hardware
    - Possible to create compilers using Coq (as VOQC), but requires a significant investment from formal verification experts. The techniques in VOQC also do not scale as they mainly consists of vector simulation.
    - Qiskit compiler is popular, but it can be buggy: Bugs4Q found 27. Giallar found other 3
    - Giallar provides a more scalable solution for Qiskit but with limitations, specifically the validation just checks if the input and output circuit perform equivalent unitaries, but it can't verify that the output circuit performs the same logical instruction as the input circuit.
  

This all leads to the main thesis proposal: I'll design and implement a compiler framework that includes built-in verification of compiler passes on arbitrary quantum programs and supports Level 2 architectures, i.e. those that incorporate error correction as a hardware abstraction.

Why is this novel?
  * No known general quantum compiler implementation so far that exposes QEC codes as a generalization of a hardware abstraction and incorporate it in its pipeline. The few compilers that compile QEC codes are implementation for specific codes.
  * Existing quantum compiler verification frameworks like VOQC have several limitations:
    - They can't scale as they try to verify matrices
    - They require very specialized knowledge on verification software like Rocq
  * Other frameworks like Giallar have more scalable approaches to circuit verification, for example it uses a finite set of replacement rules to verify that two circuits are equivalent, but it is insufficient for programs that include mid-circuit measurements or those that the used QEC to encode multiple qubits.
  * We will design, implement and use a new circuit's intermediate representation that enables these verification techniques and allows for representation of hybrid programs at different quantum abstraction layers.


