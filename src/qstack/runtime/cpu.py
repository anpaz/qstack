"""Classical processor used by the MLIR runtime."""

from __future__ import annotations

import logging

from qstack.callbacks import resolve_callback
from qstack.dialect.core import DecodeOp, SelectOp
from qstack.runtime.registry import CallbackEntry, CallbackRegistry

logger = logging.getLogger("qstack")


class CPU:
    """Owns classical runtime state and callback evaluation.

    ``qstack.select`` and ``qstack.decode`` are CPU responsibilities because
    they evaluate classical state through host-language callbacks.
    """

    def __init__(self, registry: CallbackRegistry | None = None) -> None:
        self._registry = registry if registry is not None else CallbackRegistry()
        self._source_contexts: dict[str, dict[str, object]] = {}

    def restart(self) -> None:
        self._source_contexts.clear()
        logger.debug("cpu.restart")

    def select(
        self,
        op: SelectOp,
        bits: tuple[int, ...],
    ) -> str:
        sym = op.callee.root_reference.data
        entry = self._registry.get_selector(sym)
        label = self._invoke(entry, sym, bits)
        logger.debug("cpu.select: %s %s -> %s", sym, bits, label)
        if label not in op.cases.data:
            raise RuntimeError(
                f"selector @{sym} returned label {label!r} not in menu "
                f"{list(op.cases.data)}"
            )
        return label

    def decode(
        self,
        op: DecodeOp,
        bits: tuple[int, ...],
    ) -> int:
        sym = op.callee.root_reference.data
        entry = self._registry.get_decoder(sym)
        result = int(self._invoke(entry, sym, bits))
        logger.debug("cpu.decode: %s %s -> %s", sym, bits, result)
        return result

    def _invoke(
        self,
        entry: CallbackEntry,
        symbol: str,
        bits: tuple[int, ...],
    ):
        if not entry.stateful:
            return entry.function(bits)
        source = resolve_callback(symbol).source
        context = self._source_contexts.setdefault(source, {})
        return entry.function(bits, context)
