"""Phase 2 Verify: hand-built prepare_one IR + Python selector → 1000 shots all 1.

This is the integration milestone for Phase 2: take the IR produced by
``test_prepare_one_ir._build_module`` (DESIGN.md §2.1, exact shape),
register the host-language ``@repeat_until_one`` selector, run @main
``N`` times against the runtime, and assert every shot returns the
bit ``1``.
"""

from tests.integration.test_prepare_one_ir import _build_module

from qstack_mlir.runtime import CallbackRegistry, Machine


def _build_machine() -> Machine:
    module = _build_module()
    reg = CallbackRegistry()

    @reg.selector("repeat_until_one")
    def _pick(*, b):
        return "done" if b == 1 else "retry"

    # prepare_one needs at most: 1 captured qubit from outer + 1 ancilla
    # inside the kernel. Recursion does not increase footprint because each
    # recursive call returns the same qubit threaded back. main allocates
    # 1 qubit; total worst-case = 2 wires live at once.
    return Machine(module, num_qubits=4, registry=reg)


def test_prepare_one_1000_shots_all_one() -> None:
    machine = _build_machine()
    results = machine.eval(shots=1000)
    assert all(
        r == [1] for r in results
    ), f"expected every shot to return [1], saw {sorted({tuple(r) for r in results})}"
