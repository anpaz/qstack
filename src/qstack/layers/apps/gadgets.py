from dataclasses import dataclass
from qstack.gadget import Instruction, QubitId, Gadget, GadgetContext


def new_context_with(id):
    return GadgetContext().allocate(id)


############################################
# Core instructions
############################################
def Start(name):
    return Gadget(name=name)


def PrepareZero(target):
    target = QubitId.wrap(target)
    # context = new_context_with(target)
    return Gadget(name="reset", prepare=(Instruction(name="reset", targets=[target]),))


def X(target):
    target = QubitId.wrap(target)
    return Gadget(
        name="x",
        compute=(Instruction(name="x", targets=[target]),),
    )


def H(target):
    target = QubitId.wrap(target)
    return Gadget(
        name="h",
        compute=(Instruction(name="h", targets=[target]),),
    )


def CX(ctl, target):
    ctl = QubitId.wrap(ctl)
    target = QubitId.wrap(target)
    return Gadget(
        name="cx",
        compute=(Instruction(name="cx", targets=[ctl, target]),),
    )


def Measure(target):
    target = QubitId.wrap(target)

    def passthrough_decoder(bits, context):
        return (bits, context)

    return Gadget(
        name="mz",
        measure=(Instruction(name="mz", targets=[target], parameters=None),),
        decode=passthrough_decoder,
    )


############################################
# Complex instructions
############################################
def PrepareOne(target):
    return PrepareZero(target) | X(target)


def PrepareRandom(target):
    return PrepareZero(target) | H(target)


def Entangle(ctl, target):
    return CX(ctl, target)
