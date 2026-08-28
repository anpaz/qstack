"""The kernel-only qstack core dialect.

Executable qstack programs are a closed collection of named kernels plus
opaque callback declarations. The dialect deliberately does *not* use the
``func`` dialect for program entry, calls, or indirect control flow.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar, Protocol, runtime_checkable

import numpy as np
from xdsl.dialects.builtin import (
    ArrayAttr,
    DictionaryAttr,
    IntAttr,
    StringAttr,
    SymbolNameConstraint,
    SymbolRefAttr,
)
from xdsl.ir import Dialect, ParametrizedAttribute, Region, SSAValue, TypeAttribute
from xdsl.irdl import (
    AttrSizedOperandSegments,
    IRDLOperation,
    irdl_attr_definition,
    irdl_op_definition,
    operand_def,
    prop_def,
    region_def,
    result_def,
    traits_def,
    var_operand_def,
    var_result_def,
)
from xdsl.parser import Parser
from xdsl.printer import Printer
from xdsl.traits import HasParent, IsolatedFromAbove, IsTerminator, SymbolOpInterface


@runtime_checkable
class UnitaryGateOp(Protocol):
    """Protocol implemented by executable target-dialect unitary gates."""

    def unitary(self) -> np.ndarray:
        """Return the unitary matrix in standard operand order."""


@irdl_attr_definition
class QubitType(ParametrizedAttribute, TypeAttribute):
    """``!qstack.qubit`` — a linear qubit handle."""

    name = "qstack.qubit"


@irdl_attr_definition
class BitType(ParametrizedAttribute, TypeAttribute):
    """``!qstack.bit`` — a linear classical measurement outcome."""

    name = "qstack.bit"


@irdl_attr_definition
class KernelSignatureAttr(ParametrizedAttribute):
    """Declared borrowed-input and result types of a named kernel.

    This is symbol metadata, rather than an SSA function value or callable
    type, so core IR has no first-class continuation.
    """

    name = "qstack.kernel_signature"

    inputs: ArrayAttr
    results: ArrayAttr

    @classmethod
    def from_lists(
        cls, inputs: Sequence[object], results: Sequence[object]
    ) -> "KernelSignatureAttr":
        return cls(ArrayAttr(inputs), ArrayAttr(results))


@irdl_op_definition
class KernelOp(IRDLOperation):
    """Named executable allocation scope with no SSA operation results."""

    name = "qstack.kernel"

    sym_name = prop_def(SymbolNameConstraint())
    signature = prop_def(KernelSignatureAttr)
    allocates = prop_def(IntAttr)
    body = region_def()

    traits = traits_def(IsolatedFromAbove(), SymbolOpInterface())

    def __init__(
        self,
        name: str,
        *,
        input_types: Sequence[object],
        result_types: Sequence[object],
        allocates: int,
        region: Region,
    ) -> None:
        if allocates < 0:
            raise ValueError("qstack.kernel allocates must be non-negative")
        super().__init__(
            properties={
                "sym_name": StringAttr(name),
                "signature": KernelSignatureAttr.from_lists(input_types, result_types),
                "allocates": IntAttr(allocates),
            },
            regions=[region],
        )

    @classmethod
    def parse(cls, parser: Parser) -> "KernelOp":
        """Parse ``@name <inputs, results> allocates N { ... }``."""
        name = parser.parse_symbol_name()
        signature = KernelSignatureAttr.new(KernelSignatureAttr.parse_parameters(parser))
        parser.parse_keyword("allocates")
        allocates = parser.parse_integer(allow_boolean=False, allow_negative=False)
        body = parser.parse_region()
        attributes = parser.parse_optional_attr_dict()
        kernel = cls(
            name.data,
            input_types=signature.inputs.data,
            result_types=signature.results.data,
            allocates=allocates,
            region=body,
        )
        kernel.attributes.update(attributes)
        return kernel

    def print(self, printer: Printer) -> None:
        printer.print_string(" ")
        printer.print_symbol_name(self.sym_name.data)
        printer.print_string(" ")
        self.signature.print_parameters(printer)
        printer.print_string(f" allocates {self.allocation_count} ")
        printer.print_region(self.body)
        printer.print_op_attributes(self.attributes)

    @property
    def input_types(self) -> tuple[object, ...]:
        return self.signature.inputs.data

    @property
    def declared_result_types(self) -> tuple[object, ...]:
        """The result types declared by this kernel's signature.

        This deliberately avoids ``result_types``, which is the xDSL
        ``Operation`` accessor for SSA operation results. A ``qstack.kernel``
        has no SSA results, even when its signature declares returned values.
        """
        return self.signature.results.data

    @property
    def allocation_count(self) -> int:
        return self.allocates.data


class _CallbackDeclarationOp(IRDLOperation):
    """Shared syntax for the two opaque callback declarations.

    A callback declaration is a symbol plus the size of the bit bundle it
    receives. Bits are delivered to the host as one positional tuple, so the
    declaration has no parameter names to bind and no invocation site repeats
    them.
    """

    MINIMUM_ARITY: ClassVar[int] = 0

    def __init__(self, name: str, arity: int) -> None:
        if arity < self.MINIMUM_ARITY:
            raise ValueError(f"{self.name} @{name} requires at least {self.MINIMUM_ARITY} bit inputs")
        super().__init__(
            properties={"sym_name": StringAttr(name), "arity": IntAttr(arity)}
        )

    @classmethod
    def parse(cls, parser: Parser) -> "_CallbackDeclarationOp":
        """Parse ``@name arity N``."""
        name = parser.parse_symbol_name()
        parser.parse_keyword("arity")
        arity = parser.parse_integer(allow_boolean=False, allow_negative=False)
        attributes = parser.parse_optional_attr_dict()
        declaration = cls(name.data, arity)
        declaration.attributes.update(attributes)
        return declaration

    def print(self, printer: Printer) -> None:
        printer.print_string(" ")
        printer.print_symbol_name(self.sym_name.data)
        printer.print_string(f" arity {self.input_count}")
        printer.print_op_attributes(self.attributes)

    @property
    def input_count(self) -> int:
        """The number of bits this callback receives."""
        return self.arity.data


@irdl_op_definition
class SelectorOp(_CallbackDeclarationOp):
    """A top-level opaque ``bit^n -> label`` selector declaration."""

    name = "qstack.selector"

    sym_name = prop_def(SymbolNameConstraint())
    arity = prop_def(IntAttr)
    traits = traits_def(SymbolOpInterface())

    MINIMUM_ARITY: ClassVar[int] = 0


@irdl_op_definition
class DecoderOp(_CallbackDeclarationOp):
    """A top-level opaque ``bit^n -> bit`` decoder declaration."""

    name = "qstack.decoder"

    sym_name = prop_def(SymbolNameConstraint())
    arity = prop_def(IntAttr)
    traits = traits_def(SymbolOpInterface())

    MINIMUM_ARITY: ClassVar[int] = 1


@irdl_op_definition
class MeasureOp(IRDLOperation):
    """Consume a qubit and produce a measurement bit."""

    name = "qstack.measure"

    qubit = operand_def(QubitType)
    result = result_def(BitType)

    assembly_format = "$qubit attr-dict"

    def __init__(self, *, operand: SSAValue) -> None:
        super().__init__(operands=[operand], result_types=[BitType()])


@irdl_op_definition
class ReturnOp(IRDLOperation):
    """Kernel terminator whose operands match its kernel signature exactly."""

    name = "qstack.return"

    operands_ = var_operand_def()
    traits = traits_def(IsTerminator(), HasParent(KernelOp))

    assembly_format = "($operands_^ `:` type($operands_))? attr-dict"

    def __init__(self, *, operands: Sequence[SSAValue]) -> None:
        super().__init__(operands=[list(operands)])


@irdl_op_definition
class CallOp(IRDLOperation):
    """Direct invocation of a named ``qstack.kernel``."""

    name = "qstack.call"

    callee = prop_def(SymbolRefAttr)
    arguments = var_operand_def()
    results_ = var_result_def()

    assembly_format = (
        "$callee `(` $arguments `)` attr-dict `:` functional-type($arguments, $results_)"
    )

    def __init__(
        self,
        callee: str | SymbolRefAttr,
        arguments: Sequence[SSAValue],
        result_types: Sequence[object],
    ) -> None:
        if isinstance(callee, str):
            callee = SymbolRefAttr(callee)
        super().__init__(
            operands=[list(arguments)],
            result_types=[list(result_types)],
            properties={"callee": callee},
        )


@irdl_op_definition
class DecodeOp(IRDLOperation):
    """Invoke an opaque declared decoder on a complete bit bundle."""

    name = "qstack.decode"

    callee = prop_def(SymbolRefAttr)
    bit_operands = var_operand_def(BitType)
    result = result_def(BitType)

    assembly_format = "$callee `(` $bit_operands `)` attr-dict"

    def __init__(
        self,
        *,
        callee: str | SymbolRefAttr,
        bit_operands: Sequence[SSAValue],
    ) -> None:
        if not bit_operands:
            raise ValueError("qstack.decode requires at least one bit operand")
        if isinstance(callee, str):
            callee = SymbolRefAttr(callee)
        super().__init__(
            operands=[list(bit_operands)],
            result_types=[BitType()],
            properties={"callee": callee},
        )


@irdl_op_definition
class SelectOp(IRDLOperation):
    """Select and directly invoke one named kernel from a finite case map."""

    name = "qstack.select"

    callee = prop_def(SymbolRefAttr)
    cases = prop_def(DictionaryAttr)
    bit_operands = var_operand_def(BitType)
    case_arguments = var_operand_def()
    results_ = var_result_def()

    irdl_options = (AttrSizedOperandSegments(as_property=True),)

    assembly_format = (
        "$callee `(` $bit_operands `)` `[` $case_arguments `]` "
        "$cases attr-dict `:` functional-type($case_arguments, $results_)"
    )

    def __init__(
        self,
        *,
        callee: str | SymbolRefAttr,
        bit_operands: Sequence[SSAValue],
        cases: dict[str, SymbolRefAttr],
        case_arguments: Sequence[SSAValue],
        result_types: Sequence[object],
    ) -> None:
        if not cases:
            raise ValueError("qstack.select requires at least one case")
        if isinstance(callee, str):
            callee = SymbolRefAttr(callee)
        super().__init__(
            operands=[list(bit_operands), list(case_arguments)],
            result_types=[list(result_types)],
            properties={
                "callee": callee,
                "cases": DictionaryAttr(cases),
            },
        )


QStack = Dialect(
    "qstack",
    [
        KernelOp,
        SelectorOp,
        DecoderOp,
        MeasureOp,
        ReturnOp,
        CallOp,
        DecodeOp,
        SelectOp,
    ],
    [QubitType, BitType, KernelSignatureAttr],
)
