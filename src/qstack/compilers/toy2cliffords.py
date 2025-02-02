from ..compiler import Compiler
from ..ast import QuantumInstruction
from ..layers import toy
from ..layers import cliffords_min as cliffords


def handle_flip(inst: QuantumInstruction):
    return cliffords.X(inst.targets[0])


def handle_mix(inst: QuantumInstruction):
    return cliffords.H(inst.targets[0])


def handle_entangle(inst: QuantumInstruction):
    return cliffords.CX(inst.targets[0], inst.targets[1])


class ToyCompiler(Compiler):
    def __init__(self):
        super().__init__(
            name="toy2cliffords",
            source=toy.layer,
            target=cliffords.layer,
            handlers={
                toy.Flip.name: handle_flip,
                toy.Mix.name: handle_mix,
                toy.Entangle.name: handle_entangle,
            },
        )
