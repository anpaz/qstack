from typing import Set
from qcir.circuit import Circuit, Instruction
from qstack import InstructionDefinition


def _is_valid_instruction(idx: int, instruction: Instruction, definition: InstructionDefinition):
    if list(definition.targets) != [type(t) for t in instruction.targets]:
        return f"[pos: {idx:04}]: Invalid targets for instruction {instruction.name}"

    if definition.parameters:
        for expected, actual in zip(definition.parameters, instruction.parameters):
            assert isinstance(
                actual, expected
            ), f"[pos: {idx:04}]: Expecting parameter of type {expected}, got {actual}"
    else:
        if instruction.parameters:
            return f"[pos: {idx:04}]: Not expecting parameters for instruction {instruction.name}"

    return None


def verify_instructions(
    circuit: Circuit, valid_instructions: Set[InstructionDefinition]
) -> Set[InstructionDefinition]:
    """
    Verifies that all instructions in the circuit are in valid_instructions and
    correctly follow their syntax.
    If successful, returns the set of instructions used; otherwise if fails with an assert.
    """
    instruction_set = {}
    for instr in valid_instructions:
        instruction_set[instr.name] = instr
        if instr.aliases:
            for name in instr.aliases:
                instruction_set[name] = instr

    errors = []
    instructions = set()
    for idx, inst in enumerate(circuit.instructions):
        if isinstance(inst, Instruction):
            if inst.name not in instruction_set:
                errors.append(f"[pos: {idx:04}]: Invalid instruction: {inst.name}")
            else:
                definition = instruction_set[inst.name]
                error_msg = _is_valid_instruction(idx, inst, definition)
                if error_msg:
                    errors.append(error_msg)
                else:

                    instructions.add(definition)

    error_msg = "\n".join(errors)
    assert len(errors) == 0, f"Invalid circuit:\n{error_msg}"

    return instructions
