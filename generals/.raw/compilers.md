

Let's create a summary of the following papers:

- Quantum computing with Qiskit (https://arxiv.org/pdf/2405.08810)
- QVM (https://dl.acm.org/doi/pdf/10.1145/3729290)
- "Automated Synthesis of Fault-Tolerant State Preparation Circuits for Quantum Error-Correction Codes" that appeared on PRX Quantum
- A game of surface codes (https://quantum-journal.org/papers/q-2019-03-05-128/pdf/)
- Lattice Surgery Compilation Beyond the Surface Code (https://arxiv.org/pdf/2504.10591)

The summary should follow this flow and include these ideas:
* Qiskit is typically thought mainly as an EDSL. It is, but in reality this is probably the least interesting part as the language is just a python wrapper for openqasm. 
* It has great visualizations, integration with cloud providers, and a well thought out compiler framework as explained in the document, let's provide the details of the compiler; let's not go into details that were covered in openqasm
* QVM uses Qiskit extensibility to provide abstraction for Gate Virtualization. Let's briefly explain what Gate Virtualization is; and then let's explain that they extended Qiskit's internal representation of circuits to enable this virtual gates that partition circuits but keeps track of the separation; let's also explain what they achieved with this.
* Then let's talk about "Automated Synthesis of Fault-Tolerant State Preparation Circuits" to describe how QEC and how it needs new and different compiler passes. Briefly talk about what is fault tolerant circuits, and how they are difficult to generate and therefore verification is critical to confirm they work correctly; let's explain how they verify the generated circuits.
* Then, let's talk about surface codes and how yet again new type of abstraction and compiler passes are needed as described in "A game of surface codes"; let's try to explain the surface code primitives and let's say the good news is that they are stabilizer circuits.
* Finally, let's talk about "Lattice Surgery Compilation" as an example of a compiler of qec circuits that implement the steps described in a game of surface codes, although more generically so they apply to codes other than Surface; make sure to note that the compiler is not generic, though, and only aims to compile specific type of circuits.

------------
As a reference, this is what we have for openqasm:

\textbf{OpenQASM~3}~\cite{openqasm3} extends a simple quantum assembly language (QASM) family of intermediate representations originally designed to describe quantum circuits at the gate level.  
The original QASM was an informal text format for listing gate operations used in textbooks like \cite{nielsen&chuang}, later refined into \emph{OpenQASM~2}\cite{openqasm2}, which introduced a simple grammar and minimal classical features, focusing entirely on circuit-level descriptions.  
\emph{OpenQASM~3} generalizes this model by incorporating richer classical computation, timing primitives, and pulse-level instructions, with the goal of supporting real-time interaction between classical control and quantum hardware.

Its core logical circuits syntax defines:
\begin{itemize}
  \item \textbf{Classical datatypes:} \texttt{bit} and \texttt{bool}, together with new numeric types (\texttt{int}, \texttt{float}, \texttt{angle}, and \texttt{complex}) introduced in version~3 to enable real-time arithmetic and parameterized control.
  \item \textbf{Quantum datatypes:} \texttt{qubit} and quantum registers.
  \item \textbf{Quantum gates:} built-in single- and multi-qubit gates (e.g., \texttt{x}, \texttt{y}, \texttt{z}, \texttt{h}, \texttt{cx}, \texttt{rz}), measurement via \texttt{measure}, and reinitialization via \texttt{reset}.
\end{itemize}

Beyond pure circuit specification, OpenQASM~3 adds several constructs for classical and timing behavior:
\begin{itemize}
  \item \textbf{Classical expressions and assignments:} arithmetic, logical, and comparison operators restricted to a small, implementation-oriented subset. More general computation can be delegated to host code via \texttt{extern}, which implements near-real-time control by invoking classical functions between circuit executions.
  \item \textbf{Control flow:} loops and conditional branches that may depend on measurement outcomes.
  \item \textbf{Timing primitives:} explicit scheduling with \texttt{delay}, \texttt{duration}, and timing annotations (\texttt{@t}) for device-level coordination.
  \item \textbf{Gate definitions:} user-defined composite gates can be declared as sequences of existing gates.  
  Starting with version~3, all gates are defined in terms of a single base gate \texttt{U}, whose semantics cover arbitrary single-qubit unitaries.  
  A standard library of canonical gates (e.g., \texttt{x}, \texttt{cx}, \texttt{rz}) is provided as built-in definitions over \texttt{U}.
  \item \textbf{Pulse-level primitives:} low-level operations that specify hardware control pulses, enabling descriptions of physical circuits rather than only logical ones.
\end{itemize}

While OpenQASM~3 is often described as a multi-level IR, this layering primarily spans logical (gate-level) and physical (pulse-level) program descriptions, rather than distinct quantum instruction sets.  
Its expanded control structures, numeric types, and timing model were largely shaped by IBM’s hardware and control architecture, reflecting pragmatic rather than purely language-theoretic design choices.  
The result is a unified but hardware-oriented language that bridges circuit compilation, hardware instructions, and real-time device control within a single syntactic framework.


----

the goal is to create a summary that can be used in a related work section of a thesis proposal. the thesis will be about writing a compiler framework with verified passes. related work regarding quantum programs represenation and verification has already been added.
The summary should be around 1000-1200 works long. Let's aim for clarity, though, in a way that concepts are easy to understand, so avoid long paragraphs and use enumerations when it makes sense. Keep the tone should remain direct, but not terse; and formal, but not pretentious. It should clearly explain the ideas from above. Print the summary formatted using latex.



### Compilers

* Qiskit:

* QVM:

* Automated Synthesis of Fault-Tolerant State Preparation Circuits for Quantum Error Correction Codes

* A Game of Surface Codes:

* Lattice Surgery Compiler:

