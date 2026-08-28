from qstack.runtime import CallbackRegistry, Machine
from tests.integration.test_prepare_one_ir import _build_module


def test_prepare_one_executes_from_main() -> None:
    registry = CallbackRegistry()

    @registry.selector("repeat_until_one")
    def choose(bits):
        return "done" if bits[0] else "retry"

    results = Machine(_build_module(), num_qubits=2, registry=registry).eval(shots=100)
    assert all(result == [1] for result in results)
