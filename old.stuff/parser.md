
Write a parser for qstack programs.

# Example 1

A program should be able to parse a string like:

```qstack
@stack: toy

allocate q1 q2 q3:
  mix(bias=0.8) q1
  entangle q1 q2
measure
?? vote
```

and generate a Program instance populated with the datastructures defined in qstack.ast. Specificaly for the example above, this code could be used to populate it.

```python
from qstack.layers.toy import *
from qstack import Program, Stack, Kernel

# Create a stack using the toy layer.
stack = Stack.create(layer)
qinstr = { i.name: i for i in layer.quantum_definitions }   

# Define a quantum program that allocates two qubits and entangles them.
program = Program(
    stack=stack,
    kernels=[
        Kernel.allocate(
            "q1",  # First qubit
            "q2",  # Second qubit
            compute=[
                qinstr['mix']("q1"),  # Apply a mixing operation to the first qubit.
                qinstr['entangle']("q1", "q2"),  # Entangle the first and second qubits.
            ],
        )
    ],
)
```

Notice how if specified, a stack corresponds to a specific layer in the `qstack.layers`, and all instructions must come from this layer. 

# Example 2:

This program:

```qstack
allocate q3:
  allocate q2 q1:
    ---
    ?? prepare(q=q1)
    h q2
    cx q2 q3
    cx q1 q2
    h q1
  measure
  ?? fix(q=q3)
measure
```

Should generate a program that is populated with similar code:

```python
qinstr = { i.name: i for i in teleport_layer.quantum_definitions }
cinstr = { i.name: i for i in teleport_layer.classic_definitions }

# Define the quantum program for teleportation.
program = Program(
    stack=stack,
    kernels=[
        Kernel.allocate(
            "q3",
            compute=[
                Kernel.allocate(
                    "q2",
                    "q1",
                    compute=[
                        Kernel.continue_with(Prepare(q="q1")),  # Prepare the "q1" qubit.
                        qinstr['h']("q2"),  # Create entanglement between "q2" and "q3" qubits.
                        qinstr['cx']("q2", "q3"),  # Entangle "q2" and "q3" qubits.
                        qinstr['cx']("q1", "q2"),  # Perform a Bell-state measurement.
                        qinstr['h']("q1"),  # Apply a Hadamard gate to the "q1" qubit.
                    ],
                    continue_with=cinstr['fix'](q="q3"),  # Fix the "q3" qubit's state based on measurements.
                ),
            ],
        )
    ],
)
```

In this case, the `teleport_layer` is not infered from the @stack attribute in the program, and instead is accepted as parameter.


## Parser features:

* The parser should support programs from any layer in qstack.layers as value in `@stack`
* The parser should accept an optional layer as input parameter to define the list of instructions, this will be used if `@stack` is not present. If both are present they must match.
* The parser should **not** be implemented using regex parsing, instead, it should tokenize the string and use a visitor pattern.
* There can be no changes to the current files in src/qstack
* changes should go into a new src/qstack/parser.py file


## Testing

* Write any missing tests for the parser.
* Tests should go in the /tests folder
* Use pytest as testing framework
* Don't use classes, define tests using simple `def test_` methods.
* A good way to test the parser is working is parse a string into a Program, get the string version of the Program instance, and compare with the original string.



## Expected syntax

Formally the syntax is:

```
program             :== stack kernel
stack               :== @stack: *id* | *None*
kernel              :== `allocate` target: instructions `measure` callback
instructions        :== instruction instructions | *None* 
instruction         :== op targets
                      | kernel 
callback            :== `?? ` instruction | *None*
op                  :== *id* | *id* (args)
args                :== arg | arg, args
arg                 :== `pi` | `pi/2` | `pi/4` | float | int | string |
targets             :== target | target targets
target              :== *id*
```

where strings in `` denote keywords. allow any type of blank spaces (' ', '\t', '\n')

