from dataclasses import dataclass

from qstack.emulator import Emulator
from qstack.instruction_set_definition import InstructionSetDefinition
from qstack.handler import Translator


@dataclass(frozen=True)
class Layer:
    source: InstructionSetDefinition
    target: InstructionSetDefinition = None
    emulator: Emulator | None = None
    translators: list[Translator] | None = None


def validate_layer(layer: Layer):
    error_msgs = []
    if layer.source is None:
        error_msgs.append(f"Layer has invalid source")
    if layer.target:
        for i in layer.source.instructions:
            supported = False
            for j in layer.translators:
                if i == j.supports:
                    supported = True
                    break
            if not supported:
                error_msgs.append(f"No translator for instruction: {i.name}")
    else:
        if layer.emulator is None:
            error_msgs.append(f"Layer {layer.source.name} has neither emulator nor target")

    if layer.emulator is not None:
        if layer.emulator.supports != layer.source:
            error_msgs.append(f"Layer {layer.source.name} has emulator for layer: {layer.emulator.supports.name}")

    return error_msgs
