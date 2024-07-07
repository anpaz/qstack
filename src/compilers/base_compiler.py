from abc import ABC, abstractmethod
from qcir.circuit import Circuit, Instruction, Attribute
from qstack import Handler, InstructionDefinition


class Context:
    pass


class BaseCompiler:
    def __init__(self, handlers: set[Handler]):
        self.handlers = {handler.source.name: handler for handler in handlers}

    @property
    def input_instruction_set(self) -> set[InstructionDefinition]:
        return [h.source for h in self.handlers.values()]

    @property
    def output_instruction_set(self) -> set[InstructionDefinition]:
        result = set()
        for h in self.handlers.values():
            result = result.union(h.uses)
        return result

    def compile(self, source: Circuit) -> Circuit:
        target = Circuit(source.name, [Attribute("compiler", self.__class__.__name__)])
        context = Context()

        for inst in [inst for inst in source.instructions if isinstance(inst, Instruction)]:
            assert inst.name in self.handlers, f"Missing instruction in handlers: {inst.name}"
            handler = self.handlers[inst.name]
            assert is_valid_instruction(inst, handler.source)
            target += handler.handle(inst, context)

        return target


def is_valid_instruction(instruction: Instruction, definition: InstructionDefinition):
    assert definition.targets == [type(t) for t in instruction.targets]
    if definition.parameters:
        assert definition.parameters == [type(t) for t in instruction.parameters]
    else:
        assert instruction.parameters is None
    return True
