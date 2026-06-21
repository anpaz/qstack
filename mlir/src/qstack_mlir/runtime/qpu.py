"""Shared QPU runtime contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from qstack_mlir.dialect.core import UnitaryGateOp


@dataclass(frozen=True)
class GateApplication:
    """A quantum gate operation bound to physical wire indices."""

    op: UnitaryGateOp
    qubits: tuple[int, ...]


@runtime_checkable
class QPUProtocol(Protocol):
    def restart(self) -> None: ...

    def allocate(self) -> int: ...

    def release(self, idx: int) -> None: ...

    def measure(self, idx: int) -> int: ...

    def apply_gate(self, gate: GateApplication) -> None: ...


from qstack_mlir.runtime.statevector_qpu import StateVectorQPU  # noqa: E402

QPU = StateVectorQPU
