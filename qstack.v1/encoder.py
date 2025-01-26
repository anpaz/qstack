from qstack.gadget import Gadget


def encode(gadget: Gadget, layer) -> Gadget:
    def encode_instruction(instruction):
        if isinstance(instruction, Gadget):
            return encode(instruction, layer)
        else:
            gadget = layer.encode(instruction)
            return gadget

    level = gadget.level + 1
    prepare = [encode_instruction(inst) for inst in gadget.prepare] if gadget.prepare else None
    compute = [encode_instruction(inst) for inst in gadget.compute] if gadget.compute else None
    measure = [encode_instruction(inst) for inst in gadget.measure] if gadget.measure else None
    decode = gadget.decode

    return Gadget(name=gadget.name, level=level, prepare=prepare, compute=compute, measure=measure, decode=decode)
