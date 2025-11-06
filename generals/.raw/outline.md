

# Title: Push-button verification of compilers targeting Level 2 Quantum System


## qstack

Description of qstack: 
* a simple quantum language to describe circuits.
* Similar to STIM, no classical logic.
* The core component is a quantum kernel consisting of: allocate -> compute -> measure -> callback
* compute is a list of instructions, which can be either a quantum gate (unitary) or another kernel
* classical control flow, is implemented in the callback, which can return a new kernel.
* supports dynamic memory allocations using a stack based approach
* this simple language allows to formally define pure quantum semantics, without worrying about classical control flow structures. the operational semantics are 5 rules.
* different levels of abstraction are represented as different instruction sets.
* to evaluate we created a compiler framework that proves that we can use the same representation with circuits at different levels of abstraction.
* in fact, it proves the concept that models qec codes as hardware abstractions that the compiler targets, which makes them composable and enables concatenation of codes.


## Proposed work

* we'll create a stripped down version of openqasm3 that follows a similar functionality to qstack (except the dynamic allocation of qubits). Namely we will keep:
  - Using a single base gate for all programs
  - Ability to define new gates as a sequence of existing gates
  - static classical and quantum registers
  - gate application
  - measurement and reset
  - if statements based on xor of bits
  - extern for arbitrary
  everything else will be removed
* this enables us to express the same circuits as qstack, and express Stabilizer circuits as defined in the Stabilizers circuit verification paper.
* we will define the formal operational semantics of this language, with the goal for them to be similar to qstack
* We will build a compiler framework that allows to create new passes by one of two approaches:
  1. transforming one instruction at a time
  2. transforming the entire circuit 
* We will prove using forward simulation that if you compile one instruction at a time and verify that the transformation is correct, the entire compilation is correct.
* For passes transforming entire circuits (synthesis, optimizations, scheuduling), we will use the formalism in Stabilizer circuit verification to automatically verify the outcome of the compiler, namely we will verify that the logical outcome of the input and the output programs match.
* At the end, we will have a compiler that self-verifies it is outcomes.


## Methodology and evaluation

I'll evaluate the framework by creating a compiler that transform programs with differnt quantum abstraction layers, including:

* A high level circuit that uses standard gates
* Multiple error correction codes, including:
  - Steane
  - Shor code (Repetition)
  - [[4,2,2]]
  - [[3,1,2]]
  - Surface
* Multiple hardware instruction sets, including:
  - Superconducting hardware gates
  - Ion hardware gates
  - Neutral atom hardware gates

To prove composition, we will try concatenation of passes like:

* Standard -> Steane -> Ions
* Standard -> Surface code -> Superconducting
* Standard -> [[4,2,2]] -> [[3,1,2]] -> Neutral atoms

The goal is that all passes are verified using Forward Simulation and the techniques in Quantum Hoare Logic and Stabilizers Circuit Verification to verify that each step is correct.

We will not worry too much about classical constructs in the program definition that help minimize programs size (functions, while, etc). This can be added in the future as syntactic sugar.

We will not try to implement passes for scheduling, or optimization; those are topics for a different thesis; but we expect those should work using the same framework.

## Conclusios and future work








