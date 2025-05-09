"""
Tests for the QStackParser module, which parses qstack programs into Program instances.
These tests validate the parser's ability to handle various scenarios, including stack specification, layer usage, and classical callbacks.
"""

import pytest
from qstack.parser import QStackParser
from qstack import Program, Stack
from qstack.layers.toy import layer as toy_layer
from qstack.layers.cliffords_min import layer as cliffords_min
from qstack.layer import ClassicDefinition
from qstack import Program, Stack, Kernel
from qstack.classic_processor import ClassicalContext


def prepare(context: ClassicalContext, *, q):
    """
    Classical callback for state preparation. Prepares the qubit `q` using a Hadamard gate.
    """
    return Kernel(targets=[], instructions=[cliffords_min.H(q)])


def fix(context: ClassicalContext, *, q):
    """
    Classical callback for fixing the teleported state based on measurement outcomes.
    """
    m0 = context.consume()
    m1 = context.consume()

    instructions = []
    if m1 == 1:
        instructions.append(cliffords_min.Z(q))
    if m0 == 1:
        instructions.append(cliffords_min.X(q))

    return Kernel(targets=[], instructions=instructions)


Prepare = ClassicDefinition.from_callback(prepare)
Fix = ClassicDefinition.from_callback(fix)
teleport_layer = cliffords_min.extend_with(classic={Prepare, Fix})


def test_parser_with_stack():
    """
    Test parsing a program with a specified stack. Validates that the stack and instructions are correctly parsed.
    """
    program_str = """
@stack: toy

allocate q1 q2:
  mix(bias=0.8) q1
  entangle q1 q2
measure"""

    parser = QStackParser()
    program = parser.parse(program_str)

    assert isinstance(program, Program)
    assert program.stack.target.layer == toy_layer
    assert len(program.kernels) == 1
    assert len(program.kernels[0].instructions) == 2

    print(str(program))
    assert program_str.strip() == str(program).strip()


def test_parser_with_layer():
    """
    Test parsing a program with a specified layer. Validates that the layer and instructions are correctly parsed.
    """
    program_str = """
allocate q1:
  allocate q2:    
    mix(bias=0.8) q1
    entangle q1 q2
  measure
measure"""

    parser = QStackParser(layer=toy_layer)
    program = parser.parse(program_str)

    assert isinstance(program, Program)
    assert program.stack.target.layer == toy_layer
    assert len(program.kernels) == 1
    assert len(program.kernels[0].instructions) == 1
    assert len(program.kernels) == 1
    assert len(program.kernels[0].instructions[0].instructions) == 2


def test_parser_invalid_stack():
    """
    Test parsing a program with an invalid stack name. Ensures that a ValueError is raised.
    """
    program_str = """
@stack: invalid

allocate q1 q2:    
  mix(bias=0.8) q1
  entangle q1 q2
measure"""

    parser = QStackParser()
    with pytest.raises(ValueError):
        parser.parse(program_str)


def test_parser_with_classical_callbacks():
    """
    Test parsing a program with classical callbacks. Validates that classical instructions like `prepare` and `fix` are correctly parsed.
    """
    program_str = """
allocate q3:
  allocate q2 q1:
    ?? prepare(q=q1)
    h q2
    cx q2 q3
    cx q1 q2
    h q1
  measure
  ?? fix(q=q3)
measure"""
    parser = QStackParser(layer=teleport_layer)
    program = parser.parse(program_str)
    print(program)

    assert isinstance(program, Program)
    assert program.stack.target.layer == teleport_layer
    assert len(program.kernels) == 1
    assert len(program.kernels[0].instructions) == 1
    assert isinstance(program.kernels[0].instructions[0], Kernel)
    assert program.kernels[0].instructions[0].callback.name == "fix"

    assert parser.parse(str(program)) == program


def test_get_layer_by_name():
    """
    Test the get_layer_by_name function to ensure it retrieves the correct Layer instance.
    """
    from qstack.layers import get_layer_by_name

    # Test with valid layer names
    assert get_layer_by_name("toy") == toy_layer
    assert get_layer_by_name("cliffords-min") == cliffords_min

    # Test with an invalid layer name
    with pytest.raises(ValueError):
        get_layer_by_name("nonexistent-layer")


def test_parse_simple_program():
    program_str = """
@stack: toy

allocate q1 q2:
  mix(bias=0.8) q1
  entangle q1 q2
measure
"""
    parser = QStackParser()
    program = parser.parse(program_str)
    print(program)
    assert isinstance(program, Program)
    assert str(program) == program_str.strip()
