"""
This module provides a parser for qstack programs. The parser converts a string representation of a quantum program into a Program instance.
The parser supports layers defined in qstack.layers and can handle classical callbacks.
"""

import re
from qstack import Program, Stack, Kernel
from qstack.layers import *
from qstack.layers import get_layer_by_name
from collections import namedtuple

LineInfo = namedtuple("LineInfo", ["content", "line_number"])


class ParsingError(Exception):
    def __init__(self, message, line, column):
        super().__init__(f"{message} (Line {line}, Column {column})")
        self.line = line
        self.column = column


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
            LineInfo(content=line.strip(), line_number=idx + 1)
            for idx, line in enumerate(program_str.splitlines())
            if line.strip() and not line.strip().startswith("#")
        ]
        return lines

    def parse_program(self, lines):
        stack = self.parse_stack(lines)
        kernels = self.parse_kernels(lines)
        return stack, kernels

    def parse_stack(self, lines):
        if lines and lines[0].content.startswith("@stack"):
            line_info = lines.pop(0)
            stack_name = line_info.content.split(":")[1].strip()

            if self.default_layer:
                if stack_name != self.default_layer.name:
                    raise ParsingError(
                        f"Program stack ({stack_name}) doesn't match parser's layer ({self.default_layer.name}).",
                        line_info.line_number,
                        1,
                    )
                layer = self.default_layer
            else:
                layer = get_layer_by_name(stack_name)
        elif self.default_layer:
            layer = self.default_layer
        else:
            raise ParsingError("No stack specified and no layer provided.", 1, 1)

        stack = Stack.create(layer=layer)
        self.qinstr = {i.name: i for i in layer.quantum_definitions}
        self.cinstr = {i.name: i for i in layer.classic_definitions}

        return stack

    def parse_kernels(self, lines):
        kernels = []
        while lines:
            if lines[0].content.startswith("allocate"):
                kernels.append(self.parse_kernel(lines))
            else:
                break
        return kernels

    def parse_kernel(self, lines):
        if lines[0].content.startswith("allocate"):
            allocate_line_info = lines.pop(0)
            match = re.match(r"allocate\s+([\w\s]+):", allocate_line_info.content)
            if not match:
                raise ParsingError("Invalid 'allocate' declaration.", allocate_line_info.line_number, 1)

            targets = match.group(1).split()

            instructions = []
            while lines and not lines[0].content.startswith("measure"):
                instructions.append(self.parse_instruction(lines))

            if not lines or not lines[0].content.startswith("measure"):
                raise ParsingError(
                    "Expected 'measure' keyword.", lines[0].line_number if lines else allocate_line_info.line_number, 1
                )
            lines.pop(0)  # Remove the 'measure' line

        elif lines[0].content.startswith("---"):
            targets = []
            instructions = []
            lines.pop(0)  # Remove the '---' line

        else:
            raise ParsingError("Expected 'allocate' or '---' keyword.", lines[0].line_number, 1)

        callback = None
        if lines and lines[0].content.startswith("??"):
            callback = self.parse_instruction(lines)

        return Kernel.allocate(*targets, compute=instructions, continue_with=callback)

    def parse_instruction(self, lines):
        """
        Parses a single instruction from the provided lines.

        The method processes a line of instruction, determines its type, and extracts
        the operation, arguments, and targets using a regular expression.
        """
        if lines[0].content.startswith("allocate") or lines[0].content.startswith("---"):
            return self.parse_kernel(lines)

        line_info = lines.pop(0)
        if line_info.content.startswith("??"):
            content = line_info.content[2:].strip()
            instruction_set = self.cinstr
        else:
            content = line_info.content
            instruction_set = self.qinstr

        if not content:
            raise ParsingError("Instruction content cannot be empty.", line_info.line_number, 1)

        #     - (\w+): Captures the operation name, which consists of one or more word characters.
        #     - (\(([^)]*)\))?: Optionally captures arguments enclosed in parentheses.
        #         - ([^)]*): Matches any characters inside the parentheses, excluding the closing parenthesis.
        #     - \s*: Matches zero or more whitespace characters.
        #     - (.*): Captures the remaining part of the line as targets.
        match = re.match(r"(\w+)(\(([^)]*)\))?\s*(.*)", content)
        if not match:
            raise ParsingError("Invalid instruction format.", line_info.line_number, 1)

        # Groups:
        #     1. `op`: The operation name (e.g., "allocate", "add").
        #     2. `_`: The full argument string including parentheses (e.g., "(key=value)").
        #     3. `args`: The inner content of the parentheses, representing key-value pairs (e.g., "key=value").
        #     4. `targets`: The remaining part of the line, representing target variables or parameters.
        op, _, args, targets = match.groups()
        targets = targets.split() if targets else []

        if args:
            args = {k: v for arg in args.split(",") for k, v in [arg.split("=")]}  # Parse key=value pairs
            return instruction_set[op](*targets, **args)
        else:
            return instruction_set[op](*targets)
