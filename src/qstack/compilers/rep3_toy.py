from dataclasses import replace
from ..compiler import Compiler
from ..ast import QuantumInstruction, Kernel, QubitId
from ..layers import cliffords_min as cliffords
from ..layer import ClassicDefinition
from ..processors import Outcome
from ..stack import LayerNode


def handle_x(inst: QuantumInstruction):
    return Kernel(targets=[], instructions=[cliffords.X(f"{inst.targets[0]}.{i}") for i in range(3)])


def handle_h(inst: QuantumInstruction):
    return Kernel(targets=[], instructions=[cliffords.H(f"{inst.targets[0]}.{i}") for i in range(3)])


def decode(m0: Outcome, m1: Outcome, m2: Outcome):
    if m0 + m1 + m2 > 1:
        return 1
    else:
        return 0


Decode = ClassicDefinition.from_callback(decode)


class ToyRepetitionCompiler(Compiler):
    def __init__(self):
        super().__init__(
            name="rep3_toy",
            source=cliffords.layer,
            target=replace(cliffords.layer.extend_with(classic={Decode}), name="cliffords+decoder"),
            handlers={
                cliffords.X.name: handle_x,
                cliffords.H.name: handle_h,
            },
        )

    def eval(self, kernel: Kernel, node: LayerNode):

        def build_kernel(targets):
            if len(targets) == 0:
                instructions = []
                for inst in kernel.instructions:
                    if isinstance(inst, Kernel):
                        instructions.append(self.eval(inst, node))
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
            if ":" not in callback.name:
                callback = replace(callback, name=f"{node.namespace}{kernel.callback.name}")
            return Kernel(targets="", instructions=[build_kernel(kernel.targets)], callback=callback)
