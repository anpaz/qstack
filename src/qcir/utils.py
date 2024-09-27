from typing import Callable

import logging
import random

logger = logging.getLogger("qcir")


def cache_field(instance: object, field: str, evaluator: Callable):
    if not hasattr(instance, field):
        logger.debug(f"populating field {field}")
        value = evaluator()
        object.__setattr__(instance, field, value)
    return getattr(instance, field)


def inject_random_pauli_noise(circuit, basis: str | None = None):
    from qcir import Instruction, Tick, Attribute, QubitId

    if not basis:
        basis = random.choice(["x", "y", "z"])

    def group_by_timesteps():
        block = []
        for instr in circuit.instructions:
            if isinstance(instr, Tick):
                yield block
                block = []
            else:
                block.append(instr)
        if block:
            yield block

    steps = list(group_by_timesteps())
    noisy_step = random.randint(0, len(steps) - 1)

    def new_instructions():
        for step, instructions in enumerate(steps):
            if step == noisy_step:
                only_instructions = [i for i in instructions if isinstance(i, Instruction)]
                if only_instructions:
                    noisy_instr = random.choice(only_instructions)
                    target = random.choice([t.value for t in noisy_instr.targets])
                else:
                    target = random.randint(0, circuit.qubit_count - 1)
                yield Instruction(name=basis, targets=[QubitId(target)], attributes=[Attribute("error")])
                yield Tick()
            for instr in instructions:
                yield instr
            yield Tick()

    return circuit.patch(instructions=list(new_instructions()))
