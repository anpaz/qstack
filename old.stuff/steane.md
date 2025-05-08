Unlike classical bits, which store a definite value of 0 or 1, quantum bits (qubits) encode information in a fundamentally different way. When we initialize or manipulate a qubit, we don’t directly assign it a fixed value. Instead, the qubit is placed into a superposition — a linear combination of basis states — which determines the probabilities we observe when the state is eventually measured. The probabilities are governed by complex numbers, and the full quantum state is described by their amplitudes. For a single qubit, we write this as $\alpha \ket{0} + \beta \ket{1}$, where $\alpha$ and $\beta$ are complex numbers such that $|\alpha|^2 + |\beta|^2 = 1$.

Importantly, these complex amplitudes don’t just determine measurement probabilities; they also carry **phase information** — that is, the relative angle between components of the quantum state. Even when measurement probabilities remain fixed, relative phase shifts can dramatically alter the outcomes of gate operations and multi-qubit interference. These phase relationships are critical for enabling quantum interference and entanglement, which underpin the power of quantum algorithms. But it also means that noise doesn’t just flip bits — it can also flip phases. A bit flip changes $\ket{0}$ to $\ket{1}$, while a phase flip changes $\ket{+}$ to $\ket{-}$, effectively flipping the sign of the $\ket{1}$ amplitude. Both types of errors must be accounted for in quantum error correction.

As with classical counterparts, quantum codes work by encoding one qubit of information into multiple to achieve redundancy and resist individual errors.

However, several uniquely quantum obstacles complicate this approach:

\begin{enumerate}
\item Due to the no-cloning theorem, we can’t copy quantum information into multiple qubits.
\item We can’t directly measure the state of a qubit without disturbing it.
\item Quantum errors aren’t just bit flips — they can include phase flips, or both simultaneously.
\end{enumerate}

To work around these constraints, redundancy is introduced not by copying, but by entanglement. For example, a single-qubit state $\alpha \ket{0} + \beta \ket{1}$ can be encoded as $\alpha \ket{000} + \beta \ket{111}$. Instead of inspecting individual qubit states — which would collapse the superposition — we perform parity checks across groups of qubits. These can be implemented indirectly using ancilla qubits to determine whether two or more qubits are in the same state (i.e., have even parity), without revealing what that state actually is. This strategy forms the basis for many quantum error-correcting code constructions.

This use of entanglement makes quantum codes remarkably sensitive: a single-qubit error can disturb the entire encoded state. Consider, for instance, the three-qubit state $\alpha \ket{000} + \beta \ket{111}$. If a bit-flip error (Pauli $X$) occurs on the first qubit, the state becomes $\alpha \ket{100} + \beta \ket{011}$, which is still entangled but no longer lies in the original code space. Quantum stabilizer codes are designed to detect such deviations using parity checks that span multiple qubits — without disturbing the encoded amplitudes.

These parity-check operations are called stabilizers. A stabilizer is a quantum operator that leaves valid encoded states invariant, meaning the encoded state remains unchanged when the stabilizer operator is applied — that is, the state is a $+1$ eigenstate of the stabilizer. Stabilizers composed of Pauli-$Z$ operators are used to detect **bit flip** (Pauli-$X$) errors, and are called **$Z$ stabilizers**. Similarly, stabilizers made from Pauli-$X$ operators are used to detect **phase flip** (Pauli-$Z$) errors, and are called **$X$ stabilizers**. More generally, some codes use mixed stabilizers with both $X$ and $Z$ terms to detect a broader class of errors.

A quantum error-correcting code is typically defined by a set of stabilizer operators. A quantum state is considered valid (i.e., free of detectable errors) if it is a $+1$ eigenstate of every stabilizer in the set. Measuring stabilizers doesn’t collapse the encoded state, it only tells us whether the parity constraints still hold. The result of all stabilizer measurements is collected into a bitstring called the syndrome. This syndrome doesn’t identify which specific qubit failed, but it narrows the possibilities. The syndrome decoder is the map from each syndrome to the most likely error (MLE), which can then be corrected, and the procedure that performs all measurements is the syndrome extraction routine.

In summary, the process of quantum error correction involves:

\begin{enumerate}
\item \textbf{Encoding}: spread one logical qubit across multiple physical ones using entanglement.
\item \textbf{Syndrome extraction}: measure stabilizers to detect signs of corruption without collapsing the logical state.
\item \textbf{Syndrome decoding}: analyze the syndrome to determine the most probable error.
\item \textbf{Correction}: apply the inverse operation to return to the original code space.
\end{enumerate}

As with classical codes, quantum codes are characterized by three parameters:

\begin{itemize}
\item $n$ = number of physical qubits used by the code
\item $k$ = number of logical qubits encoded
\item $d$ = code distance — the minimum number of physical qubits that must be altered to implement a nontrivial logical operation or transform one valid encoded state into another (i.e., smallest weight of a logical operator not in the stabilizer group)
\end{itemize}

For this project, we use the Steane code, a \([[7, 1, 3]]\) CSS code. It encodes 1 logical qubit into 7 physical qubits and can correct any single-qubit error. The Steane code is based on the classical Hamming code and has the property that its X and Z stabilizers are symmetric, which allows transversal logical $H$ and $CX$ operations.

We use the following stabilizers:

\[
\begin{aligned}
&[Z, Z, I, Z, Z, I, I] \\
&[Z, I, Z, Z, I, Z, I] \\
&[I, Z, Z, Z, I, I, Z] \\
&[X, X, I, X, X, I, I] \\
&[X, I, X, X, I, X, I] \\
&[I, X, X, X, I, I, X] \\
\end{aligned}
\]

with logical operators:

\[
X_L = [X, X, X, X, X, X, X], \quad
Z_L = [Z, Z, Z, Z, Z, Z, Z]
\]

Each kernel in the source program allocates a single logical qubit. The compiler transforms this into an allocation of 7 physical qubits and injects a preparation routine that initializes the code to the logical zero state. This routine prepares the logical $\ket{0}_L$ state by initializing the system to the $+1$ eigenspace of all Z stabilizers. It also inserts a classical decoder routine. For instance, the kernel:

```ruby
allocate q:
measure
```

gets compiled into:

```ruby
allocate q1.0 q1.1 q1.2 q1.3 q1.4 q1.5 q1.6:
  h q1.4
  h q1.5
  h q1.6
  cx q1.4 q1.0
  cx q1.4 q1.1
  cx q1.4 q1.3
  cx q1.5 q1.0
  cx q1.5 q1.2
  cx q1.5 q1.3
  cx q1.6 q1.1
  cx q1.6 q1.2
  cx q1.6 q1.3
measure
?? decode
```

The \`{decode} is a classical function that extracts the syndrome for the Z stabilizers and applies any needed correction; it returns the result associated with the Z logical operator, that is, by checking the overall parity of the outcome. For small codes like Steane, this is implemented using a static lookup table. For larger codes, a decoder such as minimum-weight perfect matching or a neural network may be used.

```python
def decode(m0, m1, m2, m3, m4, m5, m6):
    outcome = np.array([m0, m1, m2, m3, m4, m5, m6])
    check1 = np.dot(outcome, [1, 1, 0, 1, 1, 0, 0]) % 2
    check2 = np.dot(outcome, [1, 0, 1, 1, 0, 1, 0]) % 2
    check3 = np.dot(outcome, [0, 1, 1, 1, 0, 0, 1]) % 2
    syndrome = (check1, check2, check3)
    fault = syndrome_table.get(syndrome)

    if fault is not None:
        outcome[fault] = (outcome[fault] + 1) % 2

    return np.sum(outcome) % 2
```

A key property is that the compiled program preserves the semantics of the original: a single logical measurement is left on the measurement stack, enabling any classical postprocessing code to behave identically. The return value corresponds to a measurement of the logical $Z$ operator, computed as the parity of all 7 physical qubit outcomes.

Instructions in the original source are replaced by their logical counterparts, typically using transversal implementations. For example:

```ruby
allocate q:
  h q
measure
```

compiles to:

```ruby
allocate q1.0 q1.1 q1.2 q1.3 q1.4 q1.5 q1.6:
  ... prepare-zero ...
  h q1.0
  h q1.1
  h q1.2
  h q1.3
  h q1.4
  h q1.5
  h q1.6
measure
?? decode
```

The compiler also inserts syndrome extraction and correction \textit{between} logical instructions. For simplicity, we use a naive approach: one ancilla per stabilizer and controlled-X gates. Each stabilizer is measured by entangling an ancilla with the data qubits using controlled-Pauli gates, and then measuring the ancilla in the computational basis to infer parity. Z and X checks are split into separate subroutines. This is not a fault-tolerant scheme, but sufficient for illustrating the compiled structure.

Example for Z stabilizers:

```ruby
allocate q1.z.0 q1.z.1 q1.z.2:
  cx q1.0 q1.z.0
  cx q1.1 q1.z.0
  cx q1.3 q1.z.0
  cx q1.4 q1.z.0
  cx q1.0 q1.z.1
  cx q1.2 q1.z.1
  cx q1.3 q1.z.1
  cx q1.5 q1.z.1
  cx q1.1 q1.z.2
  cx q1.2 q1.z.2
  cx q1.3 q1.z.2
  cx q1.6 q1.z.2
measure
?? correct_z(qubit=q1)
```

And the corresponding classical oracle:

```python
def correct_z(m0, m1, m2, *, qubit):
    syndrome = (m0, m1, m2)
    fault = syndrome_table.get(syndrome)

    if fault is not None:
        target = tuple(QubitId(f"{qubit}.{i}") for i in range(7))
        return Kernel(targets=[], instructions=[cliffords.Z(target[fault])])
```

Altogether, a compiled kernel looks like:

```ruby
allocate q1.0 q1.1 q1.2 q1.3 q1.4 q1.5 q1.6:
  ... prepare-zero instructions ...

  ... correct z errors...
  ... correct x errors...
  ... logical instr ...

  ... correct z errors...
  ... correct x errors...
  ... logical instr ...

  ...

measure
?? decode
```

As with decoding, the inserted error correction routines preserve the semantics and measurement stack of the original kernel. Classical oracles in the original code continue to operate with the same semantics.
