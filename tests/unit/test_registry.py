"""Phase 2a tests: host-language callback registry.

The registry holds Python implementations of `qstack.selector` and
`qstack.decoder` MLIR declarations, keyed by symbol name. The runtime
looks up callables here when it walks `qstack.select` / `qstack.decode`.

Two top-level decorators:

    @selector("repeat_until_one")
    def _(*, b): ...

    @decoder("majority_vote")
    def _(a, b, c): ...

Both also work bare (no name → use function `__name__`).
"""

import pytest

from qstack.runtime import (
    CallbackRegistry,
    DuplicateRegistration,
    UnregisteredCallback,
)


def test_register_and_lookup_selector() -> None:
    reg = CallbackRegistry()

    @reg.selector("repeat_until_one")
    def fn(bits):
        return "done" if bits[0] == 1 else "retry"

    entry = reg.get_selector("repeat_until_one")
    assert entry.function is fn
    assert entry.function((1,)) == "done"
    assert entry.function((0,)) == "retry"


def test_register_and_lookup_decoder() -> None:
    reg = CallbackRegistry()

    @reg.decoder("majority_vote")
    def fn(bits):
        return 1 if sum(bits) >= 2 else 0

    entry = reg.get_decoder("majority_vote")
    assert entry.function is fn
    assert entry.function((1, 1, 0)) == 1
    assert entry.function((0, 1, 0)) == 0


def test_decorator_uses_function_name_when_bare() -> None:
    reg = CallbackRegistry()

    @reg.selector
    def my_selector(bits):
        return "done"

    assert reg.get_selector("my_selector").function((0,)) == "done"


def test_duplicate_registration_rejected() -> None:
    reg = CallbackRegistry()

    @reg.selector("s")
    def _(bits):
        return "x"

    with pytest.raises(DuplicateRegistration):

        @reg.selector("s")
        def _(bits):  # noqa: F811
            return "y"


def test_selectors_and_decoders_have_separate_namespaces() -> None:
    reg = CallbackRegistry()

    @reg.selector("name")
    def s(bits):
        return "done"

    @reg.decoder("name")
    def d(bits):
        return bits[0]

    assert reg.get_selector("name").function is s
    assert reg.get_decoder("name").function is d


def test_lookup_unregistered_raises() -> None:
    reg = CallbackRegistry()
    with pytest.raises(UnregisteredCallback, match="missing"):
        reg.get_selector("missing")
    with pytest.raises(UnregisteredCallback, match="missing"):
        reg.get_decoder("missing")


def test_stateful_registration_is_explicit() -> None:
    reg = CallbackRegistry()

    @reg.decoder("family:decode", stateful=True)
    def decode(bits, context):
        return bits[0] + context.get("offset", 0)

    entry = reg.get_decoder("family.2:decode")
    assert entry.function is decode
    assert entry.stateful
    assert entry == reg.get_decoder("family.3:decode")

    @reg.selector(stateful=True)
    def stateful_selector(bits, context):
        return "done"

    assert reg.get_selector("stateful_selector").stateful
