import logging
from dataclasses import replace, dataclass

from qstack.classic_processor import ClassicDefinition

from .instruction_set import InstructionSet
from .ast import Kernel, ClassicInstruction


logger = logging.getLogger("qstack")


class Compiler:

    def __init__(
        self,
        name: str,
        source: InstructionSet,
        target: InstructionSet,
        handlers: dict,
        compiler_callbacks: None | set[ClassicDefinition] = None,
    ):
        self.name = name
        self.handlers = handlers
        self.source = source
        self.target = target
        self.compiler_callbacks = compiler_callbacks or set()

        for instr in source.quantum_definitions:
            if instr.name not in self.handlers:
                logger.warning(f"Instruction {instr.name} has no handler.")

    def compile_callback(self, callback: ClassicInstruction | None):
        if callback is None:
            return None
        return replace(callback, name=f"_{self.name}_:{callback.name}")

    def compile_kernel(self, kernel: Kernel):
        instructions = []
        for inst in kernel.instructions:
            if isinstance(inst, Kernel):
                instructions.append(self.compile_kernel(inst))
            else:
                instructions.append(self.handlers[inst.name](inst))

        callback = self.compile_callback(kernel.callback)

        return replace(kernel, instructions=instructions, callback=callback)

    def create_target_callbacks(self, source_callbacks: set[ClassicDefinition]):
        def new_definition(class_definition: ClassicDefinition):
            def call_and_compile(*targets, **parameters):
                result = class_definition.callback(*targets, **parameters)
                if isinstance(result, Kernel):
                    new_kernel = self.compile_kernel(result)
                    return new_kernel
                else:
                    return result

            return ClassicDefinition(
                name=f"_{self.name}_:{class_definition.name}",
                callback=call_and_compile,
                parameters=class_definition.parameters,
            )

        return {new_definition(callback) for callback in source_callbacks}

    def compile(self, program, callbacks: set[ClassicDefinition] | None = None):
        new_definitions = self.create_target_callbacks(callbacks or set()) | self.compiler_callbacks
        new_kernels = [self.compile_kernel(kernel) for kernel in program.kernels]
        return replace(program, instruction_set=self.target, kernels=new_kernels), new_definitions
