As with classical counterparts, quantum codes work by encoding one qubit information into multiple to achieve redundancy and be resisting to individual errors.

However, there are several features that make quantum codes different:

1. Due to the no-copy theorem, information cannot be copied into multiple qubits.
2. The actual state of individual qubits is unknown.
3. Quantum errors may consists not only on bit flips, but also of phase flips.

To workaround this, instead of trying to create redundancy by copying qubit states, we use entanglement. For example, a 1 qubit state of $\alpha |0\ket + \beta |1\ket$ can be encoded as $\alpha |000\ket + \beta |111\ket$, and instead of checking for state of individual qubits, we check for the parity on qubits, which can be done without disturbing the state. For example, we can use an ancilla to check if two qubits are both in state $|0\ket$ or state $1\ket$. In general, it is possible to check the parity of any number of qubits, with many different implementations.

We call these quantum parity checks stabilizers, because they are quantum operations that will keep the quantum state stabilized (constant). We call parity checks on bits Z stabilizers, and parity checks on phase X stabilizers. It is also possible to check the parity between bits and phases using a mix of X and Z operators in the same stabilizer.

Quantum error correction codes are typically represented using a set of stabilizers. A quantum state is valid (i.e. error free) if it is stabilized (remains constant) by all stabilizers of the code.
// TODO: give a simple example.

A stabilizer identifies if the parity between a set of qubits is different, but it can't pinpoint the exact qubit that is different. What we do is we collect to the measurement from all the checks into a single bitstring, called a syndrome, and use this to identify the Most Likely Error (MLE) that generated the syndrome. We call this mapping from syndromes to MLE the syndrome decoder, and the process to collect all checks the syndrome extraction routine.

In summary, the process to apply quantum error correction is:

1. Encode the state into physical qubits.
2. Measure all the stabilizers in the code to create the syndrome (syndrome-extraction)
3. From the syndrome, identify if any data qubits need correction (syndrome-decoding)
4. Apply the correction (error-correction)

As with classical codes, there are 3 core properties that are used to describe the code capabilities:

1. n = the number of qubits the code uses for encoding
2. k = the number of qubits the code encodes
3. d = the distance of the code, i.e. the max number of bits that change between code words

For this project we decided to use the [[7, 1, 3]] Steane Code . The Steane code encodes 1 logical qubit using 7 qubits and is capable to correct any single qubit error. The Stean Code is a simple code, base on the classical Hamming code, with the property that it has seperate X and Z stabilizers (a CSS code), but more over they are symmetrical which allows for transversal logical H and CX operations.

The stabilizers we chose are:

$$
    [Z, Z, I, Z, Z, I, I] \
    [Z, I, Z, Z, I, Z, I] \
    [I, Z, Z, Z, I, I, Z] \
    [X, X, I, X, X, I, I] \
    [X, I, X, X, I, X, I] \
    [I, X, X, X, I, I, X] \
$$

With logical operators:

$$
X = [X, X, X, X, X, X, X] \
Z = [Z, Z, Z, Z, Z, Z, Z] \
$$

For every Kernel in the source code, our compiler allocates 7 qubits and injects a prepare-zero routine that prepres the qubits into the necessary stabilizer state; then it also invokes a classical decoder function, i.e., this kernel:

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
>> decode
```

`decode` is a classical function that first extracts the syndrome by checking the parity of each one of the stabilizer checks, and return by applying the Z logical operator, that is, by checking the overall parity of the outcome:

```python
def decode(m0: Outcome, m1: Outcome, m2: Outcome, m3: Outcome, m4: Outcome, m5: Outcome, m6: Outcome):
    outcome = np.array([m0, m1, m2, m3, m4, m5, m6])
    check1 = int(np.dot(outcome, np.array([1, 1, 0, 1, 1, 0, 0])) % 2)
    check2 = int(np.dot(outcome, np.array([1, 0, 1, 1, 0, 1, 0])) % 2)
    check3 = int(np.dot(outcome, np.array([0, 1, 1, 1, 0, 0, 1])) % 2)
    syndrome = (check1, check2, check3)
    fault = syndrome_table.get(syndrome)
    logger.debug(f"outcome: {outcome}, syndrome: {syndrome}, correction: {fault}")

    if fault is not None:
        outcome[fault] = (outcome[fault] + 1) % 2

    return int(np.sum(outcome) % 2)
```

A key property to highlight of the compiled program is that its semantics do not change. After evaluating the compiled kernel the measurement stack will still include a single measurement, so if the original source included a classical oracle after the measurement, the same oracle can be invoked in the compiled program with the same values and same semantics.

Instructions in the original source are replaced with their corresponding logical counterpart, since most instructions are transversal, this means that we just apply the same instructions to all corresponding qubits, therefore:

```ruby
allocate q:
  h q
measure
```

gets compiled into:

```ruby
allocate q1.0 q1.1 q1.2 q1.3 q1.4 q1.5 q1.6:
  ... prepare-zero instructions ...
  h q1.0
  h q1.1
  h q1.2
  h q1.3
  h q1.4
  h q1.5
  h q1.6
measure
>> decode
```

We also incorporate syndrome extraction and error correction _between_ logical instructions, to detect and correct any errors introduced. As mentioned there are many possible techniques for syndrome extraction, some more fault-tolerant than others. Without lost of generalization, we chose the naive implementation that performns parity checks using one ancilla per check and Controlled X instructions; we also chose to split this into two routines, one for X and one for Z stabilizers. Overall, the process consists of allocating the ancillas, entangle them with the data qubits using CX operations, and measure them to detect parities. These measurements then go to a classical oracle that based on the measurements decides if a correction is needed or not. All in all, the Kernel used for Z syndrome extraction and correction is:

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
    >> correct_z(qubit=q1)
```

with the `correct_z` oracle defined as:

```python
def correct_z(m0: Outcome, m1: Outcome, m2: Outcome, *, qubit: QubitId):
    syndrome = (m0, m1, m2)
    fault = syndrome_table.get(syndrome)

    if fault is not None:
        target = tuple([QubitId(f"{qubit}.{i}") for i in range(7)])
        return Kernel(targets=[], instructions=[cliffords.Z(QubitId(f"{qubit}.{target[fault]}"))])
    else:
        return None
```

so an entire kernel compilation consists of:

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
>> decode
```

As with measurement and decoding, the introduction of the syndrome extraction and error correction does not change the semantics of the original code, nor does it have any affect the measurement stack, which allows for any classical oracle in the original program to continue working with the same semantics.
