"""Core qstack dialect — types and ops (Phase 1a + 1b).

Adds: !qstack.qubit, !qstack.bit, qstack.kernel, qstack.measure, qstack.return.
The linearity / kernel-signature verifier comes in Phase 1.1 as a separate
module-level pass.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from xdsl.dialects.builtin import (  # noqa: F401  (ModuleOp re-exported indirectly)
    ArrayAttr,
    DictionaryAttr,
    FunctionType,
    ModuleOp,
    StringAttr,
    SymbolRefAttr,
)
from xdsl.ir import Dialect, ParametrizedAttribute, Region, SSAValue, TypeAttribute
from xdsl.irdl import (
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
from xdsl.traits import HasParent, IsTerminator


@runtime_checkable
class UnitaryGateOp(Protocol):
    """Protocol implemented by executable compute-gate ops."""

    def unitary(self) -> np.ndarray:
        """Return the op's unitary matrix in standard qubit order."""


@irdl_attr_definition
class QubitType(ParametrizedAttribute, TypeAttribute):
    """`!qstack.qubit` — a linear handle to a qubit register.

    Single-use semantics are enforced by the module-level verifier
    (`qstack.verifier`), not by xdsl's structural checks.
    """

    name = "qstack.qubit"


@irdl_attr_definition
class BitType(ParametrizedAttribute, TypeAttribute):
    """`!qstack.bit` — a classical measurement outcome.

    Linear, single-use; see `QubitType` for the verifier note.
    """

    name = "qstack.bit"


@irdl_op_definition
class KernelOp(IRDLOperation):
    """`qstack.kernel` — allocation scope.

    Signature: ``() -> (bit × a, qubit × b)``.
    * The op has no qubit operands. Borrowed qubits are captured from the
      enclosing SSA scope.
    * The single region's entry block lists ``a`` allocated qubits as block
      arguments.
    * Results are the ``a`` surfaced measurement bits followed by the ``b``
      threaded-back captured qubits. Linearity of `!qstack.qubit` forces every
      captured outer qubit to appear exactly once in this trailing position.
    """

    name = "qstack.kernel"

    results_ = var_result_def()  # bits then qubits; checked by module verifier
    body = region_def()

    assembly_format = "$body attr-dict `:` `(` `)` `->` type($results_)"

    def __init__(
        self,
        *,
        result_types: list,
        region: Region,
    ) -> None:
        super().__init__(
            result_types=[list(result_types)],
            regions=[region],
        )


@irdl_op_definition
class MeasureOp(IRDLOperation):
    """`qstack.measure %q : !qstack.qubit -> !qstack.bit`.

    Consumes the qubit, produces a bit. May only appear inside a `qstack.kernel`
    body (checked by the module verifier in Phase 1.1).
    """

    name = "qstack.measure"

    qubit = operand_def(QubitType)
    result = result_def(BitType)

    assembly_format = "$qubit attr-dict"

    def __init__(self, *, operand: SSAValue) -> None:
        super().__init__(operands=[operand], result_types=[BitType()])


@irdl_op_definition
class ReturnOp(IRDLOperation):
    """`qstack.return %m, %q0, ...` — terminator for a `qstack.kernel` body.

    Operand list mirrors the enclosing kernel's result list: bits first,
    threaded-back qubits second.
    """

    name = "qstack.return"

    operands_ = var_operand_def()
    traits = traits_def(IsTerminator(), HasParent(KernelOp))

    assembly_format = "($operands_^ `:` type($operands_))? attr-dict"

    def __init__(self, *, operands: list[SSAValue]) -> None:
        super().__init__(operands=[list(operands)])


@irdl_op_definition
class SelectOp(IRDLOperation):
    """`qstack.select @callee(name = %b, ...) continuations { label = @sym, ... } : <fn-type>`.

    Host-language callback site. Consumes a bundle of named bit operands,
    yields one of the named continuation symbols as an SSA value of MLIR
    function type. Operand-name → operand alignment is positional: the
    `i`-th entry of `bit_names` names the `i`-th `bit_operands` value.

    Symbol presence and signature matching against `callee`'s declaration are
    Phase 1.1 verifier concerns, not IRDL constraints.
    """

    name = "qstack.select"

    callee = prop_def(SymbolRefAttr)
    bit_names = prop_def(ArrayAttr[StringAttr])
    continuations = prop_def(DictionaryAttr)

    bit_operands = var_operand_def(BitType)
    result = result_def(FunctionType)

    def __init__(
        self,
        *,
        callee: SymbolRefAttr,
        bit_names: list[str],
        bit_operands: list[SSAValue],
        continuations: dict[str, SymbolRefAttr],
        result_type: FunctionType,
    ) -> None:
        if len(bit_names) != len(bit_operands):
            raise ValueError(
                f"bit_names ({len(bit_names)}) and bit_operands ({len(bit_operands)}) " "must have the same length"
            )
        super().__init__(
            operands=[list(bit_operands)],
            result_types=[result_type],
            properties={
                "callee": callee,
                "bit_names": ArrayAttr([StringAttr(n) for n in bit_names]),
                "continuations": DictionaryAttr(dict(continuations)),
            },
        )


@irdl_op_definition
class DecodeOp(IRDLOperation):
    """`qstack.decode @callee(%b1, %b2, ...) : (!qstack.bit, ...) -> !qstack.bit`.

    Pure classical bit-to-bit host-language call. Has no menu and no quantum
    effect. Symbol presence + arity matching are verifier concerns.
    """

    name = "qstack.decode"

    callee = prop_def(SymbolRefAttr)
    bit_operands = var_operand_def(BitType)
    result = result_def(BitType)

    def __init__(
        self,
        *,
        callee: SymbolRefAttr,
        bit_operands: list[SSAValue],
    ) -> None:
        if len(bit_operands) < 1:
            raise ValueError("qstack.decode requires at least one bit operand")
        super().__init__(
            operands=[list(bit_operands)],
            result_types=[BitType()],
            properties={"callee": callee},
        )


@irdl_op_definition
class InvokeOp(IRDLOperation):
    """`qstack.invoke %fn(%a, %b, ...) : (...) -> (...)`.

    Indirect call through a function-typed SSA value, typically the result of
    `qstack.select`. DESIGN.md spells this site as `func.call_indirect`, but
    xdsl does not ship that op; `qstack.invoke` is the in-dialect substitute
    with identical semantics. See implementation-notes for the deviation.
    """

    name = "qstack.invoke"

    callee = operand_def(FunctionType)
    args = var_operand_def()
    results_ = var_result_def()

    def __init__(
        self,
        *,
        callee: SSAValue,
        args: list[SSAValue],
        result_types: list,
    ) -> None:
        super().__init__(
            operands=[callee, list(args)],
            result_types=[list(result_types)],
        )


QStack = Dialect(
    "qstack",
    [KernelOp, MeasureOp, ReturnOp, SelectOp, DecodeOp, InvokeOp],
    [QubitType, BitType],
)
