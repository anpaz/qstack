# qstack

qstack is a framework for compiling and executing quantum programs using a stack-based approach for dynamic qubit allocation and measurement. It provides tools for defining quantum kernels, compiling them into lower-level instructions, integrating classical computations, and incorporating quantum error correction seamlessly.

## Installation

To install qstack, run:

```bash
pip install .
```

## Key Features

- **Dynamic Qubit Allocation**: Allocate and measure qubits dynamically using a stack-based approach, enabling flexible and modular program design.
- **Quantum Kernels**: Define quantum operations in a modular and nested manner, supporting complex quantum workflows.
- **Classical Oracles**: Integrate classical computations into quantum programs, allowing conditional logic and hybrid quantum-classical operations.
- **Instruction Set Compilation**: Compile high-level quantum instructions into hardware-specific low-level operations, ensuring compatibility with diverse quantum hardware.
- **Quantum Error Correction**: Leverage modularity to incorporate advanced quantum error correction techniques, such as the Steane code, into the compilation of programs. This ensures resilience against errors and supports fault-tolerant quantum computation.
- **Independent QPU and CPU Interfaces**: Demonstrates the independent operation of quantum and classical processors, showcasing their respective capabilities and interactions.

## Usage

Explore the `examples/` directory for sample usage of qstack. Some key examples include:

- `bell.py`: Demonstrates creating a Bell state.
- `teleport.py`: Implements quantum teleportation using entanglement and classical communication.
- `noisy_bell.py`: Simulates a Bell state with noise, introducing realistic quantum system modeling.
- `steane.py`: Demonstrates quantum error correction using the Steane code, showcasing fault-tolerant quantum computation.
- `cpu.py`: Highlights the independent operation of the classical processor (CPU) for handling classical logic and measurement results.
- `qpu.py`: Highlights the independent operation of the quantum processor (QPU) for executing quantum instructions.

Run an example using:

```bash
python examples/steane.py
```

## High-Level Syntax Examples

qstack supports a high-level syntax for defining quantum programs. Here are a couple of examples:

### Example 1: Bell State

```plaintext
allocate q1:
  h q1
  allocate q2:
    cx q1 q2
  measure
measure
```

### Example 2: Quantum Teleportation

```plaintext
allocate q1:
  allocate q2:
    allocate q3:
      h q2
      cx q2 q3
      cx q1 q2
      h q1
    measure
  measure
  ?? apply_corrections(q1)
measure q3
```

## Documentation

The core functionality of qstack is implemented under the `src/qstack/` directory. Key modules include:

- `compiler.py`: Handles the compilation of quantum programs, including error correction.
- `emulator.py`: Simulates quantum program execution, supporting both noiseless and noisy environments.
- `layer.py`: Defines abstraction layers for quantum operations, such as the Toy and clifford_min layers.
- `noise.py`: Models noise in quantum computations, enabling realistic simulations.
- `stack.py`: Implements the stack-based qubit allocation and measurement, central to qstack's design.
- `classic_processor.py` and `qpu.py`: Define the independent interfaces for classical and quantum processors, respectively.

Refer to the source code for detailed implementation and extendability.

## License

This project is licensed under the standard MIT License. See the LICENSE file for details.