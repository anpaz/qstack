"""Runtime backend-compatibility analyses."""

from __future__ import annotations

from dataclasses import dataclass

from xdsl.dialects.builtin import ModuleOp

from qstack.dialect.core import UnitaryGateOp


@dataclass(frozen=True)
class StimCompatibility:
    """Result of checking whether a module can run on ``StimQPU``."""

    ok: bool
    reason: str | None = None


class StimCompatibilityError(ValueError):
    """Raised when explicit STIM execution is requested for unsupported IR."""


def check_stim_compatible(module: ModuleOp) -> StimCompatibility:
    """Return whether all executable quantum gates are in the Clifford dialect.

    The lowered MLIR operation stream is the source of truth for backend
    selection. Surface includes are intentionally ignored because modules can
    be constructed directly or rewritten by compiler passes.
    """

    for op in module.walk():
        if isinstance(op, UnitaryGateOp) and not op.name.startswith("cliffords."):
            return StimCompatibility(
                ok=False,
                reason=f"STIM only supports cliffords.* gates for now; found {op.name}",
            )
    return StimCompatibility(ok=True)


def is_stim_compatible(module: ModuleOp) -> bool:
    return check_stim_compatible(module).ok


def require_stim_compatible(module: ModuleOp) -> None:
    result = check_stim_compatible(module)
    if not result.ok:
        raise StimCompatibilityError(result.reason or "module is not STIM-compatible")
