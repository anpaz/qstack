"""
This module provides a parser for qstack programs. The parser converts a string representation of a quantum program into a Program instance.
The parser supports layers defined in qstack.layers and can handle classical callbacks.
"""

import re
from qstack import Program
from qstack.ast import ClassicInstruction, Kernel
from qstack.instruction_sets import get_instruction_set_by_name
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

    def __init__(self, instruction_set=None):
        self.default_instruction_set = instruction_set
        self.qinstr = {i.name: i for i in instruction_set.quantum_definitions} if instruction_set else {}

    def parse(self, program_str):
        lines = self.split_lines(program_str)
        inst_set, kernels = self.parse_program(lines)
        return Program(instruction_set=inst_set, kernels=kernels)

    def split_lines(self, program_str):
        lines = [
            LineInfo(content=line.strip(), line_number=idx + 1)
            for idx, line in enumerate(program_str.splitlines())
            if line.strip() and not line.strip().startswith("#")
        ]
        return lines

    def parse_program(self, lines):
        layer = self.parse_instruction_set(lines)
        kernels = self.parse_kernels(lines)
        return layer, kernels

    def parse_instruction_set(self, lines):
        if lines and lines[0].content.startswith("@instruction-set"):
            line_info = lines.pop(0)
            inst_set_name = line_info.content.split(":")[1].strip()

            if self.default_instruction_set:
                if inst_set_name != self.default_instruction_set.name:
                    raise ParsingError(
                        f"Program instruction-set ({inst_set_name}) doesn't match parser's layer ({self.default_instruction_set.name}).",
                        line_info.line_number,
                        1,
                    )
                instruction_set = self.default_instruction_set
            else:
                instruction_set = get_instruction_set_by_name(inst_set_name)
        elif self.default_instruction_set:
            instruction_set = self.default_instruction_set
        else:
            raise ParsingError("No instruction-set specified and no layer provided.", 1, 1)

        self.qinstr = {i.name: i for i in instruction_set.quantum_definitions}
        return instruction_set

    def parse_kernels(self, lines):
        kernels = []
        while lines:
            if lines[0].content.startswith("allocate") or lines[0].content.startswith("---"):
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
            callback = self.parse_callback(lines)

        return Kernel.allocate(*targets, instructions=instructions, callback=callback)

    def parse_instruction(self, lines):
        """
        Parses a single instruction from the provided lines.

        The method processes a line of instruction, determines its type, and extracts
        the operation, arguments, and targets using a regular expression.
        """
        if lines[0].content.startswith("allocate") or lines[0].content.startswith("---"):
            return self.parse_kernel(lines)

        line_info = lines.pop(0)
        content = line_info.content

        if not content:
            raise ParsingError("Instruction content cannot be empty.", line_info.line_number, 1)

        #     - (\w+): Captures the operation name, which consists of one or more word characters.
        #     - (\(([^)]*)\))?: Optionally captures arguments enclosed in parentheses.
        #         - ([^)]*): Matches any characters inside the parentheses, excluding the closing parenthesis.
        #     - \s*: Matches zero or more whitespace characters.
        #     - (.*): Captures the remaining part of the line as targets.
        match = re.match(r"(\w+)(\(([^)]*)\))?\s*(.*)", content)
        if not match:
            raise ParsingError(f"Invalid instruction format {content}.", line_info.line_number, 1)

        # Groups:
        #     1. `op`: The operation name (e.g., "allocate", "add").
        #     2. `_`: The full argument string including parentheses (e.g., "(key=value)").
        #     3. `args`: The inner content of the parentheses, representing key-value pairs (e.g., "key=value").
        #     4. `targets`: The remaining part of the line, representing target variables or parameters.
        op, _, args, targets = match.groups()
        targets = targets.split() if targets else []

        if args:
            args = {k: v for arg in args.split(",") for k, v in [arg.split("=")]}  # Parse key=value pairs
            return self.qinstr[op](*targets, **args)
        else:
            return self.qinstr[op](*targets)

    def parse_callback(self, lines):
        """
        Parses a callback instruction.

        The method processes a line of instruction, determines its type, and extracts
        the operation, arguments, and targets using a regular expression.
        """
        line_info = lines.pop(0)
        if line_info.content.startswith("??"):
            content = line_info.content[2:].strip()
        else:
            raise ParsingError(
                "Invalid callback instruction: callbacks must start with '??'.", line_info.line_number, 1
            )

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

        if targets:
            raise ParsingError("Callback instructions should not have targets.", line_info.line_number, 1)

        if args:
            args = {k: v for arg in args.split(",") for k, v in [arg.split("=")]}  # Parse key=value pairs
            return ClassicInstruction(name=op, parameters=args)
        else:
            return ClassicInstruction(name=op, parameters={})
