"""Classical processor used by the MLIR runtime."""

from __future__ import annotations

import logging

from xdsl.dialects.func import FuncOp

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

    def select(self, op: SelectOp, bit_values: dict[str, int], funcs: dict[str, FuncOp]) -> FuncOp:
        sym = op.callee.root_reference.data
        fn = self._registry.get_selector(sym)
        label = fn(**bit_values)
        logger.debug("cpu.select: %s %s -> %s", sym, bit_values, label)
        if label not in op.continuations.data:
            raise RuntimeError(
                f"selector @{sym} returned label {label!r} not in menu "
                f"{list(op.continuations.data)}"
            )
        cont_sym = op.continuations.data[label]
        cont_name = cont_sym.root_reference.data
        if cont_name not in funcs:
            raise RuntimeError(f"continuation @{cont_name} not in module")
        return funcs[cont_name]

    def decode(self, op: DecodeOp, args: list[int]) -> int:
        sym = op.callee.root_reference.data
        fn = self._registry.get_decoder(sym)
        result = int(fn(*args))
        logger.debug("cpu.decode: %s %s -> %s", sym, args, result)
        return result
