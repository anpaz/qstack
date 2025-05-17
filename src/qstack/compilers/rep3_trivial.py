from dataclasses import replace
from ..compiler import Compiler
from ..ast import QuantumInstruction, Kernel, QubitId
from ..instruction_sets import cliffords_min as cliffords
from ..classic_processor import ClassicalContext, ClassicDefinition


def handle_x(inst: QuantumInstruction):
    return Kernel(targets=[], instructions=[cliffords.X(f"{inst.targets[0]}.{i}") for i in range(3)])


def handle_h(inst: QuantumInstruction):
    return Kernel(targets=[], instructions=[cliffords.H(f"{inst.targets[0]}.{i}") for i in range(3)])


def decode(context: ClassicalContext):
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

    def compile_kernel(self, kernel: Kernel):
        def build_kernel(targets):
            if len(targets) == 0:
                instructions = []
                for inst in kernel.instructions:
                    if isinstance(inst, Kernel):
                        instructions.append(self.compile_kernel(inst))
                    else:
                        instructions.append(self.handlers[inst.name](inst))
                return Kernel(targets=[], instructions=instructions)
            else:
                qubits = tuple([QubitId(f"{targets[0]}.{i}") for i in range(3)])
                return Kernel(targets=qubits, instructions=[build_kernel(targets[1:])], callback=Decode())

        callback = kernel.callback
        if callback is None:
            return build_kernel(kernel.targets)
        else:
            callback = self.compile_callback(callback)
            return Kernel(targets="", instructions=[build_kernel(kernel.targets)], callback=callback)
