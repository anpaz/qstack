from dataclasses import replace
from ..compiler import Compiler
from ..ast import QuantumInstruction, Kernel, QubitId
from ..instruction_sets import cliffords_min as cliffords
from ..classic_processor import ClassicContext, ClassicDefinition


def handle_x(inst: QuantumInstruction):
    return Kernel(target=None, instructions=[cliffords.X(f"{inst.targets[0]}.{i}") for i in range(3)])


def handle_h(inst: QuantumInstruction):
    return Kernel(target=None, instructions=[cliffords.H(f"{inst.targets[0]}.{i}") for i in range(3)])


def decode(context: ClassicContext):
    m0 = context.consume()
    m1 = context.consume()
    m2 = context.consume()
    if m0 + m1 + m2 > 1:
        context.collect(1)
    else:
        context.collect(0)


Decode = ClassicDefinition.from_callback(decode)


class TrivialRepetitionCompiler(Compiler):
    def __init__(self):
        super().__init__(
            name="rep3-trivial",
            source=cliffords.instruction_set,
            target=cliffords.instruction_set,
            handlers={
                cliffords.X.name: handle_x,
                cliffords.H.name: handle_h,
            },
            compiler_callbacks={Decode},
        )

    def decode(self, context):
        m0 = context.consume()
        m1 = context.consume()
        m2 = context.consume()
        if m0 + m1 + m2 > 1:
            context.collect(1)
        else:
            context.collect(0)

    def compile_kernel(self, kernel: Kernel):
        # Build list of compiled instructions
        instructions = []
        for inst in kernel.instructions:
            if isinstance(inst, Kernel):
                instructions.append(self.compile_kernel(inst))
            else:
                instructions.append(self.handlers[inst.name](inst))

        # Handle the case where there are targets (logical qubit)
        if kernel.target:
            # Use Kernel.allocate to create nested structure for 3 physical qubits
            qubits = [f"{kernel.target}.{i}" for i in range(3)]

            # If there's an original callback, the wrapped version (via wrap_callbacks)
            # already includes decode. Otherwise, use standalone Decode.
            callback = self.compile_callback(kernel.callback) or Decode()
            return Kernel.allocate(*qubits, instructions=instructions, callback=callback)
        else:
            # No targets, just return kernel with instructions and callback
            final_callback = self.compile_callback(kernel.callback)
            return Kernel(target=None, instructions=instructions, callback=final_callback)
