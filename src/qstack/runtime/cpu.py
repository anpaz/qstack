"""Classical processor used by the MLIR runtime."""

from __future__ import annotations

import logging

from qstack.dialect.core import DecodeOp, SelectOp
from qstack.runtime.registry import CallbackRegistry

logger = logging.getLogger("qstack")


class CPU:
    """Owns classical runtime state and callback evaluation.

    ``qstack.select`` and ``qstack.decode`` are CPU responsibilities because
    they evaluate classical state through host-language callbacks.
    """

    def __init__(self, registry: CallbackRegistry | None = None) -> None:
        self._registry = registry if registry is not None else CallbackRegistry()

    def restart(self) -> None:
        logger.debug("cpu.restart")

    def select(self, op: SelectOp, bits: tuple[int, ...]) -> str:
        sym = op.callee.root_reference.data
        fn = self._registry.get_selector(sym)
        label = fn(bits)
        logger.debug("cpu.select: %s %s -> %s", sym, bits, label)
        if label not in op.cases.data:
            raise RuntimeError(
                f"selector @{sym} returned label {label!r} not in menu "
                f"{list(op.cases.data)}"
            )
        return label

    def decode(self, op: DecodeOp, bits: tuple[int, ...]) -> int:
        sym = op.callee.root_reference.data
        fn = self._registry.get_decoder(sym)
        result = int(fn(bits))
        logger.debug("cpu.decode: %s %s -> %s", sym, bits, result)
        return result
