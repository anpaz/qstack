"""Base class for MLIR op rewriting compiler passes.

Provides traversal, handler dispatch, and result replacement logic.
Subclasses only need to provide a handler registry (mapping op types to handler functions).
"""

from xdsl.dialects.builtin import ModuleOp
from xdsl.dialects.func import FuncOp
from xdsl.ir import Block, Operation


class BaseOpRewriter:
    handlers: dict

    def __init__(self):
        if not hasattr(self, "handlers"):
            raise NotImplementedError(
                "Subclasses must define a 'handlers' dict mapping op types to handler functions."
            )

    def compile(self, module: ModuleOp) -> ModuleOp:
        for op in module.body.ops:
            if isinstance(op, FuncOp) and not op.is_declaration:
                self._rewrite_block(op.body.block)
        return module

    def _rewrite_block(self, block: Block) -> None:
        for op in list(block.ops):
            self._rewrite_op(op)

    def _rewrite_op(self, op: Operation) -> None:
        for region in op.regions:
            for nested in region.blocks:
                self._rewrite_block(nested)
        handler = self.handlers.get(type(op))
        if handler is None:
            return
        handler(op)
