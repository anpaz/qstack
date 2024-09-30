Each layer needs:

- an instruction set
- a compiler
- a backend

The compiler

- takes a Circuit or a Kernel.
- checks the instruction set, if already in the instruction set it just returns the same circuit as a kernel (or the same kernel)
- otherwise, it checks one by one its known compilers, if the compiler takes the circuit's instruction set it uses the corresponding compiler
- backends should take a noise_model

The backend

Takes a Kernel and evaluates it

TODO

- add noise support for pyquil
- layout and scheduling
- pauli frame tracking

###

Using different layers of abstraction has been a critical pattern in computing. It's easy to forget that a computer basically controls a set of transistors and send them signals to turn them or on off. Instead, we define an architecture of the machine, and expose intructions to read and write into memory registers and perform some basic binary operations and expose this via an assembly language. But not even that, of course, practically nobody tries to write a sorting algorithm in assembly, instead we have higher level languages like C, which in turn can be very complicated and error prone, so we program in Python, and so on... It is then the role of the compiler to take a program in a higher level instruction set and compile it into the intructions of a lower level.

The same principles apply to quantum programs. Quantum devices change the state of individual atoms/particles via pulses, however we don't program a quantum computer by specifying the pulses that must be applied, instead, it exposes a small set of instructions representing operations or gates that can be applied to a qubit (an observable representing a two dimensional property of a particle). Even more, the instructions that a device can implement depend on the physical implementation of the device itself (ions vs neutral atoms vs semiconductors), so instead of creating programs specific to the device quantum programmers use a standard set of unitaries to program a device, which then need to be decomposed into the actual instructions supported by the device.

So there are plenty of similarities between a classical and a quantum stack, but there are also plenty of differences. One main critical difference is that a quantum device must manipulate qubits via Unitaries, instead of bits via binary operations. Another big difference is that as opposed to the classical stack the quantum stack is not necessarily meant to enable more expressiveness (quantum operations are represented as matrix, and as such are much more expressive than binary operations) but the goal is mainly to enable a more consistent programming experience.

Connectivity adds another layer of complexity to quantum programs. Even though in principle quantum instructions can be applied to any qubit, in practice operations can only be applied to certain qubits based on their physical location on the devices, so on some devices two qubit operations can only be applied to qubits that are physically next to each other; other devices might require that one qubit operations are applied only to qubits who are physicall in an Interaction Zone.

Quantum error correction adds yet another level of complexity that we need to abstract. Quantum computers are probabilistic in nature, and we model their instruction via matrices, that encode how the probabilities of measuring an observable change; but errors can often happen and as such using techniques similar to classical models in which the state of a single qubit is encoded into multiple qubits provide a mechanism to improve resiliance. This mechanism is added as another layer in the stack applied between the set of standard instructions and the instructions supported by the hardware.

The goal is to create a software stack for quantum progrms that offers full visibility of the transformations that happen on each layer; we want the stack also to be completely flexible to allow us to mix and match layers. For example, test the same quantum program using different QEC code, or maybe the same QEC code with different backends, or maybe we want to test a program when running with no error correction directly against different backends.

Current quantum programming languages and their compilers are focused on NISQ devices, so they basically have 2 layers: a layer with standard gates and a hardware specific layer, with the following assumptions:

- There is a 1-1 mapping of qubits, each qubit in the circuit corresponds to some qubit in hardare.
- Any quantum instructions can be expressed in terms of a basis gate set corresponding to the instructions implemented by hardware.

This is problematic in the context of error correction. Logical qubits are grouped into blocks, and there is not a direct mapping from logical qubits to physical qubits. Instructions are applied at the block level, and previous instructions on the block affect how instructions are applied.

Finally, all quantum programs are hybrid in nature, meaning, a quantum program must execute not only a list of quantum instructions on the quantum hardware, but they must take decisions and collect classical data resulting from the execution of such instructions. The problem is that quantum devices are not efficient at executing binary operations, so the execution of the classical instructions is typically delegated to a classical processor running together with the quantum processor. This has had the effect that all quantum programming languages and representations include both classical and quantum components that must be managed together.

All these constraints have created a very fraction ecosystem in which no truly QISA exist and each physical device has its own compiler. Some standardization efforts exist, for example with the adoption of QIR across multiple vendors, however noone has been able to successfully integrate an instruction set that incorporates an error correction layer.

With qstack we offer a new ISA in which we embrace the hybrid nature of quantum programs, but mark a clear seperation between the classical and quantum instructions; in fact, we focus solely on the quantum instruction set and just define a simple interface that defines the classical instruction set completely open. This creates a very simple, yet flexible quantum instruction set that can be used across all layers of the quantum stack, and that makes it straight forward to mix and match different instructions set, for different type of hardwares or for different quantum error correction schemes.

# QCIR

## Abstract

This paper discusses the use of different layers of abstraction in quantum computing, drawing parallels with classical computing. The aim is to highlight the necessity and benefits of abstraction in the design and implementation of quantum instruction set architectures (QISAs). Through a detailed analysis of quantum programming, connectivity constraints, quantum error correction, and the hybrid nature of quantum programs, we propose the QStack as a novel approach to QISA, offering a flexible and standardized quantum instruction set.

## Introduction

Abstraction layers are a fundamental concept in computing, facilitating the management of complexity. In classical computing, the transition from hardware control of transistors to high-level programming languages like Python demonstrates the evolution and importance of these layers. Similarly, quantum computing requires a structured approach to manage the intricate details of quantum hardware.

## Classical vs. Quantum Computing

In classical computing, a computer's primary function is to control transistors by sending signals to turn them on or off. However, the complexity of programming at this level necessitated the development of architectures that expose instructions for memory read/write and basic binary operations, encapsulated in assembly languages. Further abstraction led to high-level languages like C and Python, with compilers translating these into lower-level instructions.

Quantum computing parallels this structure. Quantum devices manipulate the states of particles using pulses. However, quantum programming does not involve direct control of these pulses. Instead, a set of instructions, or gates, represents operations on qubits (two-dimensional properties of particles). The specific instructions a device can execute depend on its physical implementation (ions, neutral atoms, semiconductors), necessitating a standardized set of unitary operations that can be decomposed into device-specific instructions.

## Key Differences in Quantum Computing

Despite similarities, significant differences exist between classical and quantum computing stacks. Quantum devices operate on qubits using unitary transformations rather than bits with binary operations. The quantum stack aims not for greater expressiveness—quantum operations are inherently more expressive as matrices—but for a consistent programming experience.

Connectivity introduces additional complexity. Although quantum instructions can theoretically apply to any qubit, practical limitations arise from qubits' physical locations. Some devices restrict two-qubit operations to adjacent qubits or single-qubit operations to specific interaction zones.

Quantum error correction further complicates this landscape. Quantum computers are inherently probabilistic, and errors necessitate encoding single-qubit states into multiple qubits for resilience. This error correction layer integrates between the standard instructions and the hardware-specific instructions.

## Hybrid Nature of Quantum Programs

Quantum programs are inherently hybrid, requiring the execution of both quantum and classical instructions. Quantum devices are inefficient at binary operations, so classical instructions typically run on a classical processor alongside the quantum processor. Consequently, quantum programming languages and representations have historically include both classical and quantum components mixed in the same instruction set.

## Fragmented Ecosystem and QStack Proposal

The constraints and complexities of quantum computing have resulted in a fragmented ecosystem lacking a unified QISA. While standardization efforts like QIR have made strides, no comprehensive instruction set incorporates an error correction layer.

Our proposed QStack offers a new ISA, embracing the hybrid nature of quantum programs while clearly separating classical and quantum instructions. By focusing solely on the quantum instruction set and defining a simple interface for classical instructions, QStack provides a flexible and straightforward quantum instruction set. This approach allows seamless integration across different hardware types and quantum error correction schemes.

## Conclusion

Abstraction layers are crucial in both classical and quantum computing. By drawing parallels and highlighting the unique challenges of quantum computing, we propose QStack as a robust solution for standardizing quantum instruction sets, enhancing compatibility and flexibility across the quantum stack.

---

### References

- M. A. Nielsen and I. L. Chuang, "Quantum Computation and Quantum Information," Cambridge University Press, 2010.
- A. W. Cross et al., "Open Quantum Assembly Language," arXiv preprint arXiv:1707.03429, 2017.
- M. Schuld and F. Petruccione, "Supervised Learning with Quantum Computers," Springer, 2018.
- P. Krysta et al., "QIR: Quantum Intermediate Representation," Microsoft Quantum, 2020.
