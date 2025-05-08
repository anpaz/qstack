"""
This module provides a parser for qstack programs. The parser converts a string representation of a quantum program into a Program instance.
The parser supports layers defined in qstack.layers and can handle classical callbacks.
"""

from qstack import Program, Stack, Kernel
from qstack.layers import *
from qstack.layers import get_layer_by_name


class QStackParser:
    """
    Parses qstack programs into Program instances. The parser supports specifying a stack via @stack or using an optional layer parameter.
    """

    def __init__(self, layer=None):
        self.default_layer = layer
        self.qinstr = {i.name: i for i in layer.quantum_definitions} if layer else {}
        self.cinstr = {i.name: i for i in layer.classic_definitions} if layer else {}

    def parse(self, program_str):
        lines = self.split_lines(program_str)
        stack, kernels = self.parse_program(lines)
        return Program(stack=stack, kernels=kernels)

    def split_lines(self, program_str):
        lines = [
            line.strip() for line in program_str.splitlines() if line.strip() and not line.strip().startswith("#")
        ]
        return lines

    def parse_program(self, lines):
        stack = self.parse_stack(lines)
        kernels = self.parse_kernels(lines)
        return stack, kernels

    def parse_stack(self, lines):
        layer = None
        if lines and lines[0].startswith("@stack"):
            line = lines.pop(0)
            parts = line.split(":", 1)
            if len(parts) != 2 or not parts[1].strip():
                raise ValueError("Invalid @stack declaration. Expected format '@stack: <name>'.")
            stack_name = parts[1].strip()

            if self.default_layer:
                if stack_name != self.default_layer.name:
                    raise ValueError("Program stack doesn't match parser's layer.")
                layer = self.default_layer
            else:
                layer = get_layer_by_name(stack_name)
        elif self.default_layer:
            layer = self.default_layer
        else:
            raise ValueError("No stack specified and no layer provided.")

        stack = Stack.create(layer=layer)
        self.qinstr = {i.name: i for i in layer.quantum_definitions}
        self.cinstr = {i.name: i for i in layer.classic_definitions}

        return stack

    def parse_kernels(self, lines):
        kernels = []
        while lines:
            if lines[0].startswith("allocate"):
                kernels.append(self.parse_kernel(lines))
            else:
                break
        return kernels

    def parse_kernel(self, lines):
        if not lines or not lines[0].startswith("allocate"):
            raise ValueError("Expected 'allocate' keyword.")

        allocate_line = lines.pop(0).strip()[:-1].split()
        if allocate_line[0] != "allocate":
            raise ValueError("Expected 'allocate' keyword.")
        targets = allocate_line[1:] if len(allocate_line) > 1 else []

        instructions = []
        while lines and not lines[0].startswith("measure"):
            instructions.append(self.parse_instruction(lines))

        if not lines or not lines[0].startswith("measure"):
            raise ValueError("Expected 'measure' keyword.")
        lines.pop(0)

        callback = None
        if lines and lines[0].startswith("??"):
            callback = self.parse_instruction(lines)

        return Kernel.allocate(*targets, compute=instructions, continue_with=callback)

    def parse_instruction(self, lines):
        if lines[0].startswith("allocate"):
            return self.parse_kernel(lines)

        # Split operation and targets
        line = lines.pop(0).strip()
        parts = line.split()
        if not parts:
            raise ValueError("Invalid instruction format.")

        op = parts[0]
        if op == "??":
            op = parts[1].strip()
            targets = []
            instruction_set = self.cinstr
        else:
            targets = parts[1:] if len(parts) > 1 else []
            instruction_set = self.qinstr

        # Check if operation has arguments in parentheses
        if "(" in op and op.endswith(")"):
            op_name, args = op.split("(", 1)
            args = args.rstrip(")").split(",")
            args = {k: v for arg in args for k, v in [arg.split("=")]}

            return instruction_set[op_name](
                *targets,
                **args,
            )
        else:
            return instruction_set[op](*targets)
