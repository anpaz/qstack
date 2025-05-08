import logging
from dataclasses import replace

from .layer import Layer
from .ast import Kernel


logger = logging.getLogger("qstack")


class Compiler:

    def __init__(self, name: str, source: Layer, target: Layer, handlers: dict):
        self.name = name
        self.handlers = handlers
        self.source = source
        self.target = target

        for instr in source.quantum_definitions:
            if instr.name not in self.handlers:
                logger.warning(f"Instruction {instr.name} has no handler.")

    def eval(self, kernel, node):

        instructions = []
        for inst in kernel.instructions:
            if isinstance(inst, Kernel):
                instructions.append(self.eval(inst, node))
            else:
                instructions.append(self.handlers[inst.name](inst))

        callback = kernel.callback
        if (callback is not None) and (":" not in callback.name):
            callback = replace(callback, name=f"{node.namespace}{kernel.callback.name}")

        return replace(kernel, instructions=instructions, callback=callback)

    def compile(self, program):
        new_stack = program.stack.add_layer(compiler=self, layer=self.target)
        new_kernels = [self.eval(kernel, new_stack.target.lower.lower) for kernel in program.kernels]
        return replace(program, stack=new_stack, kernels=new_kernels)
