"""Base class for non-mutating MLIR compiler passes.

Public compilation clones the input module, then rewrites the clone. Subclasses
only need to provide a handler registry mapping operation types to handlers.
"""

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Block, Operation

from qstack.dialect.core import KernelOp


class BaseOpRewriter:
    handlers: dict

    def __init__(self):
        if not hasattr(self, "handlers"):
            raise NotImplementedError(
                "Subclasses must define a 'handlers' dict mapping op types to handler functions."
            )

    def compile(self, module: ModuleOp) -> ModuleOp:
        """Return a rewritten copy of ``module`` without modifying ``module``."""
        output = module.clone()
        for op in output.body.ops:
            if isinstance(op, KernelOp):
                self._rewrite_block(op.body.block)
        return output

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
