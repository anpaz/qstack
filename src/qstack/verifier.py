"""Module-level linearity + kernel-signature verifier (Phase 1.1).

Rules — see ``tests/unit/test_verifier.py`` for the exhaustive list and one
negative test per rule:

1. Every `!qstack.qubit` SSA value has exactly one use.
2. Every `!qstack.bit` SSA value has exactly one use.
3. `qstack.kernel` signature: result list is `bit × a` followed by
   `qubit × b`, where `a` is the entry-block argument count (allocations).
   The number of trailing qubit results `b` is whatever the body threaded
   back from outer-scope captures; linearity of `!qstack.qubit` enforces
   the borrow-return symmetry without a kernel-specific rule.
4. `qstack.return` operand list matches the enclosing kernel's result types
   exactly (positionally), which already pins bits-then-qubits ordering.

Symbol-table checks (selector / decoder declarations match their call sites)
land alongside the surface-language lowering, when those symbols always exist.
"""

from __future__ import annotations

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Operation, SSAValue

from qstack.dialect.core import BitType, KernelOp, QubitType, ReturnOp


class LinearityError(Exception):
    """Raised when the module violates a qstack linearity or signature rule."""


def _check_single_use(value: SSAValue, where: str) -> None:
    """A linear value must be used exactly once."""
    n = len(list(value.uses))
    if n == 0:
        raise LinearityError(f"linear value {value!r} ({value.type}) is unused at {where}")
    if n > 1:
        raise LinearityError(f"linear value {value!r} ({value.type}) has multiple uses ({n}) at {where}")


def _is_linear(value: SSAValue) -> bool:
    return isinstance(value.type, (QubitType, BitType))


def _verify_kernel(kernel: KernelOp) -> None:
    region = kernel.body
    if len(region.blocks) != 1:
        raise LinearityError(f"qstack.kernel must have exactly one block, got {len(region.blocks)}")
    entry = region.blocks[0]

    # Signature: block args are `allocations × a`; results are
    # `bits × a` then `qubits × b`. Borrowed qubits are captured from the
    # enclosing scope; their count `b` is read off the result list, and the
    # linearity check (run earlier) already ensures every capture has its
    # single use — which can only be satisfied by threading it back as one
    # of the trailing qubit results.
    n_alloc = len(entry.args)
    results = list(kernel.results)
    n_bits = sum(1 for r in results if isinstance(r.type, BitType))
    n_qubits = sum(1 for r in results if isinstance(r.type, QubitType))

    if n_bits != n_alloc:
        raise LinearityError(
            f"qstack.kernel signature: {n_alloc} allocations but {n_bits} bit " "results (must match)"
        )

    expected_types = [BitType()] * n_bits + [QubitType()] * n_qubits
    actual_types = [r.type for r in results]
    if [type(t) for t in actual_types] != [type(t) for t in expected_types]:
        raise LinearityError(
            "qstack.kernel result order must be bits-then-qubits, got " f"{[t.name for t in actual_types]}"
        )

    # qstack.return operands must positionally match the kernel result types.
    terminator = entry.last_op
    if not isinstance(terminator, ReturnOp):
        raise LinearityError(f"qstack.kernel body must end in qstack.return, got {type(terminator).__name__}")
    ret_operand_types = [op.type for op in terminator.operands]
    if [type(t) for t in ret_operand_types] != [type(t) for t in expected_types]:
        raise LinearityError(
            "qstack.return operand types must match enclosing kernel result types; "
            f"expected {[t.name for t in expected_types]}, got "
            f"{[t.name for t in ret_operand_types]}"
        )


def _walk_block_for_ops(op: Operation, callback) -> None:
    callback(op)
    for region in op.regions:
        for blk in region.blocks:
            for child in blk.ops:
                _walk_block_for_ops(child, callback)


def verify_module(module: ModuleOp) -> None:
    """Run the qstack module-level verifier. Raises ``LinearityError`` on the
    first rule violation."""

    def check_op_results(op: Operation) -> None:
        for result in op.results:
            if _is_linear(result):
                _check_single_use(result, f"result of {op.name}")

    def check_kernel_signature(op: Operation) -> None:
        if isinstance(op, KernelOp):
            _verify_kernel(op)

    def check_block_args(op: Operation) -> None:
        for region in op.regions:
            for blk in region.blocks:
                for arg in blk.args:
                    if _is_linear(arg):
                        _check_single_use(arg, f"block arg in {op.name}")

    for top in module.body.ops:
        # Linearity (uses) first so unused/multiple-use diagnostics surface
        # before structural ones.
        _walk_block_for_ops(top, check_block_args)
        _walk_block_for_ops(top, check_op_results)
        _walk_block_for_ops(top, check_kernel_signature)
