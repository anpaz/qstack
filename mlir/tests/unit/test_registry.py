"""Phase 2a tests: host-language callback registry.

The registry holds Python implementations of `qstack.selector` and
`qstack.decoder` MLIR declarations, keyed by symbol name. The emulator
looks up callables here when it walks `qstack.select` / `qstack.decode`.

Two top-level decorators:

    @selector("repeat_until_one")
    def _(*, b): ...

    @decoder("majority_vote")
    def _(a, b, c): ...

Both also work bare (no name → use function `__name__`).
"""

import pytest

from qstack_mlir.runtime import (
    CallbackRegistry,
    DuplicateRegistration,
    UnregisteredCallback,
)


def test_register_and_lookup_selector() -> None:
    reg = CallbackRegistry()

    @reg.selector("repeat_until_one")
    def fn(*, b):
        return "done" if b == 1 else "retry"

    assert reg.get_selector("repeat_until_one") is fn
    assert reg.get_selector("repeat_until_one")(b=1) == "done"
    assert reg.get_selector("repeat_until_one")(b=0) == "retry"


def test_register_and_lookup_decoder() -> None:
    reg = CallbackRegistry()

    @reg.decoder("majority_vote")
    def fn(a, b, c):
        return 1 if (a + b + c) >= 2 else 0

    assert reg.get_decoder("majority_vote") is fn
    assert reg.get_decoder("majority_vote")(1, 1, 0) == 1
    assert reg.get_decoder("majority_vote")(0, 1, 0) == 0


def test_decorator_uses_function_name_when_bare() -> None:
    reg = CallbackRegistry()

    @reg.selector
    def my_selector(*, b):
        return "done"

    assert reg.get_selector("my_selector")(b=0) == "done"


def test_duplicate_registration_rejected() -> None:
    reg = CallbackRegistry()

    @reg.selector("s")
    def _(*, b):
        return "x"

    with pytest.raises(DuplicateRegistration):

        @reg.selector("s")
        def _(*, b):  # noqa: F811
            return "y"


def test_selectors_and_decoders_have_separate_namespaces() -> None:
    reg = CallbackRegistry()

    @reg.selector("name")
    def s(*, b):
        return "done"

    @reg.decoder("name")
    def d(a):
        return a

    assert reg.get_selector("name") is s
    assert reg.get_decoder("name") is d


def test_lookup_unregistered_raises() -> None:
    reg = CallbackRegistry()
    with pytest.raises(UnregisteredCallback, match="missing"):
        reg.get_selector("missing")
    with pytest.raises(UnregisteredCallback, match="missing"):
        reg.get_decoder("missing")
