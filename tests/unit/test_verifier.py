"""Phase 1.1 tests: linearity + kernel-signature module-level verifier.

Rules enforced by `qstack.verifier.verify_module`:

* Every `!qstack.qubit` SSA value has exactly one use.
* Every `!qstack.bit` SSA value has exactly one use.
* `qstack.kernel` signature: the result list is `bit × a` then `qubit × b`,
  where `a` is the entry-block argument count (allocations). Equivalently,
  `bits = allocations`. The trailing `qubit × b` count is whatever the body
  threaded out from outer-scope captures; linearity already enforces the
  borrow-return symmetry without a kernel-specific rule.
* `qstack.return` operand list matches the enclosing kernel's result types
  exactly.

Symbol-presence / declaration-signature checks for selectors and decoders
are out of scope for Phase 1.1 — they land with the surface lowering when
declarations always exist.
"""

import pytest
from xdsl.dialects.builtin import FunctionType, ModuleOp
from xdsl.dialects.func import FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import CxOp, HOp
from qstack.dialect.core import KernelOp, MeasureOp, ReturnOp
from qstack.verifier import LinearityError, verify_module


def _wrap_in_main(kernel: KernelOp, *, outer_qubit_types=None) -> ModuleOp:
    """Wrap a kernel in a host @main that consumes its results."""
    outer_qubit_types = list(outer_qubit_types or [])
    main_block = Block(arg_types=outer_qubit_types)
    main_block.add_op(kernel)
    main_block.add_op(FuncReturn.create(operands=list(kernel.results)))
    fn = FuncOp(
        "main",
        FunctionType.from_lists(outer_qubit_types, [r.type for r in kernel.results]),
        Region([main_block]),
    )
    return ModuleOp([fn])


def _minimal_good_module() -> ModuleOp:
    """Single allocation, single measurement, no captures — verifier-clean."""
    blk = Block(arg_types=[QubitType()])
    q0 = blk.args[0]
    meas = MeasureOp(operand=q0)
    blk.add_op(meas)
    blk.add_op(ReturnOp(operands=[meas.result]))
    kernel = KernelOp(result_types=[BitType()], region=Region([blk]))
    return _wrap_in_main(kernel)


def test_minimal_kernel_passes() -> None:
    verify_module(_minimal_good_module())


def test_unused_qubit_fails() -> None:
    """Allocate q0 and never use it — verifier rejects."""
    blk = Block(arg_types=[QubitType()])
    blk.add_op(ReturnOp(operands=[]))
    kernel = KernelOp(result_types=[], region=Region([blk]))
    m = _wrap_in_main(kernel)
    with pytest.raises(LinearityError, match="unused"):
        verify_module(m)


def test_double_used_bit_fails() -> None:
    """Measure once, return the bit twice — second use is illegal."""
    blk = Block(arg_types=[QubitType()])
    q0 = blk.args[0]
    meas = MeasureOp(operand=q0)
    blk.add_op(meas)
    blk.add_op(ReturnOp(operands=[meas.result, meas.result]))
    kernel = KernelOp(
        result_types=[BitType(), BitType()],
        region=Region([blk]),
    )
    m = _wrap_in_main(kernel)
    with pytest.raises(LinearityError, match="multiple uses"):
        verify_module(m)


def test_kernel_signature_bits_count_mismatch_fails() -> None:
    """2 allocations but only 1 bit in result list (signature lies)."""
    blk = Block(arg_types=[QubitType(), QubitType()])
    q0, q1 = blk.args
    h = HOp(q0)
    blk.add_op(h)
    cx = CxOp(h.result, q1)
    blk.add_op(cx)
    meas = MeasureOp(operand=cx.target_out)
    blk.add_op(meas)
    blk.add_op(ReturnOp(operands=[meas.result, cx.control_out]))
    kernel = KernelOp(
        result_types=[BitType(), QubitType()],
        region=Region([blk]),
    )
    m = _wrap_in_main(kernel)
    with pytest.raises(LinearityError, match="bit results"):
        verify_module(m)


def test_dropped_capture_fails_linearity() -> None:
    """Capture an outer qubit but drop it inside the body — linearity catches.

    With the no-operands kernel design, "borrow-return symmetry" is enforced
    by qubit linearity, not a kernel-specific signature rule: the H result
    on the captured qubit is unused, so the unused-value check fires.
    """
    outer = Block(arg_types=[QubitType()])
    captured = outer.args[0]
    inner = Block(arg_types=[])
    h = HOp(captured)
    inner.add_op(h)
    inner.add_op(ReturnOp(operands=[]))
    kernel = KernelOp(result_types=[], region=Region([inner]))
    outer.add_op(kernel)
    outer.add_op(FuncReturn.create(operands=[]))
    fn = FuncOp("host", FunctionType.from_lists([QubitType()], []), Region([outer]))
    m = ModuleOp([fn])
    with pytest.raises(LinearityError, match="unused"):
        verify_module(m)


def test_kernel_results_ordering_fails() -> None:
    """Results in wrong order: qubit then bit instead of bits-first."""
    outer = Block(arg_types=[QubitType()])
    captured = outer.args[0]

    inner = Block(arg_types=[QubitType()])  # 1 allocation
    q_alloc = inner.args[0]
    meas = MeasureOp(operand=q_alloc)
    inner.add_op(meas)
    # WRONG ORDER: qubit first, bit second.
    inner.add_op(ReturnOp(operands=[captured, meas.result]))

    kernel = KernelOp(
        result_types=[QubitType(), BitType()],  # WRONG: bits must come first
        region=Region([inner]),
    )
    outer.add_op(kernel)
    outer.add_op(FuncReturn.create(operands=list(kernel.results)))
    fn = FuncOp(
        "host",
        FunctionType.from_lists([QubitType()], [QubitType(), BitType()]),
        Region([outer]),
    )
    m = ModuleOp([fn])
    with pytest.raises(LinearityError, match="order"):
        verify_module(m)
