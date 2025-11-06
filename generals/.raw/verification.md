\section{Verification of Quantum Programs and Compilers}
\label{sec:verification}

Verifying the correctness of quantum programs and compilers has become a central challenge as the complexity of quantum software increases. 
Unlike classical programs, quantum programs cannot be fully tested: measuring a quantum state irreversibly alters it, and simulation becomes infeasible as the number of qubits grows.
This section reviews the main approaches to program and compiler verification, from classical verification foundations to recent developments in quantum circuit verification. 
We organize these efforts by their verification models and scalability, focusing on those that target compiler transformations.

\subsection{From Classical to Quantum: Forward Simulation}

The foundation of verified compilation lies in the concept of \emph{forward simulation}, formalized by Leroy in the CompCert compiler~\cite{leroy2009compcert}. 
CompCert is a fully verified compiler for a large subset of the C language, developed in the Rocq (formerly Coq) proof assistant.
Its key idea is that a compiler is correct if, for every source program $P$ and corresponding compiled program $P'$, the observable behaviors of $P'$ are included in those of $P$.

Formally, given small-step semantics $\rightarrow_S$ and $\rightarrow_T$ for the source and target languages, a \emph{simulation relation} $R$ is defined over states of the two semantics.
Compiler correctness is established by proving:
\[
  s_S \;R\; s_T \;\wedge\; s_S \rightarrow_S s_S' \;\Rightarrow\; \exists s_T'.\; s_T \rightarrow_T^* s_T' \wedge s_S' \;R\; s_T'
\]
That is, each step of the source program can be simulated by one or more steps in the target, preserving the relation $R$.
If the source semantics is deterministic, this implies behavioral inclusion, ensuring that compilation preserves program meaning.
This proof pattern composes cleanly: once each compiler pass is verified under forward simulation, their composition is also correct.
Forward simulation thus provides a scalable and modular approach to compiler verification.

When applied to quantum circuits, this notion translates naturally:
a compiler pass is correct if the unitary or superoperator implemented by the output circuit is semantically equivalent to that of the input circuit.
However, unlike in classical compilation, quantum states are continuous and high-dimensional, making direct semantic comparison difficult.
This motivates verification strategies that exploit structure—stabilizers, symbolic representations, or algebraic reasoning—to reason about circuits more efficiently.

\subsection{The Case for Verification: Why Testing Quantum Programs Fails}

The need for formal verification in quantum programming is highlighted by Rovara et al.'s framework for debugging quantum programs~\cite{rovara2025framework}.
The authors argue that debugging quantum software is fundamentally more difficult than classical debugging for several reasons:

\begin{enumerate}
  \item A single quantum operation affects the entire system state due to entanglement.
  \item Measurement collapses superposition, making it impossible to inspect intermediate states nondestructively.
  \item The global state space grows exponentially with the number of qubits, making full simulation intractable.
\end{enumerate}

Their framework introduces assertion-based debugging primitives that allow developers to express expected properties of quantum states, such as belonging to a specific subspace or being separable.
While useful for small programs, these assertions depend on full-state simulation and are therefore limited in scalability.
This directly motivates verification techniques that reason symbolically or algebraically about program semantics rather than by exhaustive simulation.

\subsection{Program Verification via Quantum Hoare Logic}

An early attempt to adapt formal reasoning to quantum programs is \textbf{Quantum Hoare Logic (QHL)}~\cite{feng2021quantum}.
QHL extends classical Hoare logic to reason about quantum states using density matrices and superoperators.
Assertions take the form of Hermitian operators that represent subspaces or observables, and correctness judgments are expressed as:
\[
  \{A\}\; P\; \{B\}
\]
meaning that executing program $P$ on any input state satisfying $A$ results in an output satisfying $B$.
QHL provides sound and (relatively) complete rules for both partial and total correctness and supports programs that mix classical and quantum variables.

Although conceptually elegant, QHL is computationally expensive: verifying a program requires reasoning over full density matrices, which scales exponentially with the number of qubits.
As a result, QHL provides an important theoretical foundation but cannot yet be applied to realistic circuits or compilers.

\subsection{Compiler Verification in VOQC}

The \textbf{Verified Optimizing Quantum Compiler (VOQC)}~\cite{voqc2021} extends ideas from CompCert into the quantum domain.
VOQC is built entirely within Rocq and uses two embedded languages:
\emph{QWIRE}, a high-level quantum circuit language, and \emph{SQIR}, a low-level intermediate representation (IR).
QWIRE programs are built compositionally within Rocq, enabling formal reasoning about their semantics.
SQIR, in turn, models circuits as sequences of primitive gates with explicit qubit indices, making it suitable for formal verification of compiler passes.

Correctness proofs in VOQC follow a structure similar to forward simulation.
Each transformation is proven to preserve the semantics of the circuit, defined as its unitary matrix representation.
All proofs are mechanized in Rocq, and the compiler can be extracted to executable OCaml code.
While powerful, VOQC primarily handles circuits without measurement and does not directly reason about compilers written in external languages.

\subsection{Template-Based Verification in Giallar}

The \textbf{Giallar} framework~\cite{tao2022giallar} takes a pragmatic approach to quantum compiler verification.
Instead of defining a new quantum language, Giallar verifies existing \texttt{Qiskit} compiler passes, one of the most widely used toolchains in practice.
It does so by validating transformations at two levels:

\begin{enumerate}
  \item \textbf{Rewrite-rule verification:} Each circuit rewrite rule (e.g., commutation or gate fusion) is formally proven correct in Coq.
  \item \textbf{Pass verification:} Giallar checks that a compiler pass transforms a circuit only through the application of these verified rules.
\end{enumerate}

This reduces verification of large compiler passes to the application of a small, trusted rule set.
The approach scales better than state-based techniques and can catch real errors in production compilers.
In addition, Giallar can reason about the \emph{classical control logic} of compiler passes by combining symbolic execution with the Z3 SMT solver, allowing limited verification of the pass implementation itself.

In their evaluation, the authors verified $44$ of $56$ passes in Qiskit, uncovering several previously unknown bugs.
Unsupported features include randomized algorithms, approximate synthesis, and pulse-level control, all outside the formal model.

\subsection{Lightweight Reasoning via the Heisenberg Picture}

The paper \textbf{Hoare Meets Heisenberg}~\cite{sundaram2022hoare} proposes a new logic that achieves scalability by shifting from the Schrödinger to the \emph{Heisenberg} picture of quantum mechanics.
In the Schrödinger view, the program transforms the \emph{state}, while in the Heisenberg view, it transforms the \emph{observables} (operators) instead.
This reversal has profound verification implications:
\begin{itemize}
  \item The state space grows exponentially, but the space of observables can often be represented compactly.
  \item For Clifford (stabilizer) circuits, the transformation of observables is linear and efficiently computable.
\end{itemize}

The logic propagates postconditions backward through the program by applying the corresponding Heisenberg transformation to the assertions.
This makes it possible to reason efficiently about large Clifford circuits, including those that appear in quantum error correction and measurement-based computing.
The system is expressive enough to reason about ancilla disposal, separability, transversality, and post-measurement states, and it extends to certain non-Clifford gates such as $T$ and controlled unitaries through approximation.

\subsection{Verifying Stabilizer Circuits}

Building on the same Heisenberg intuition, Kliuchnikov, Beverland, and Paetznick introduced a comprehensive framework for \textbf{stabilizer circuit verification}~\cite{kliuchnikov2023stabilizer}.
They formalize a complete description of stabilizer circuits that includes classical control on measurement outcomes, under the restriction that such control is conditioned only on parities of prior measurements.
This restriction ensures that equivalence checking remains efficient and avoids the \#P-hardness of more general conditional control.

Their method verifies equivalence of two circuits by computing their \emph{logical action} on the stabilizer generators and measurement outcomes, rather than simulating states.
Equivalence holds if and only if both circuits induce the same transformation on these generators.
This logical-level view allows verification of entire code-encoding or code-switching circuits, as used in lattice surgery or fault-tolerant computation.

Although the paper focuses on quantum error correction circuits, the same reasoning applies to any stabilizer circuit.
Even a physical circuit can be seen as a logical circuit implementing the trivial $[[1,1,1]]$ code, making this framework a unifying approach to verifying circuit transformations at any level of abstraction.

\subsection{Summary}

Across these works, we observe a clear evolution in verification strategies:

\begin{enumerate}
  \item \textbf{Forward simulation} (CompCert) establishes a modular foundation for compiler verification.
  \item \textbf{Assertion-based debugging} exposes why testing quantum programs is insufficient.
  \item \textbf{Quantum Hoare logic} introduces formal reasoning about quantum state transformations but lacks scalability.
  \item \textbf{VOQC} applies forward simulation to quantum compilation within Rocq.
  \item \textbf{Giallar} bridges theory and practice by verifying real-world compiler passes via pre-verified rewrite rules.
  \item \textbf{Heisenberg-style reasoning} (Hoare Meets Heisenberg, Stabilizer Circuit Verification) offers a scalable path by transforming observables instead of states.
\end{enumerate}

These approaches together illustrate the trajectory from formal semantics to scalable verification, paving the way for practical, formally verified quantum compilers.
