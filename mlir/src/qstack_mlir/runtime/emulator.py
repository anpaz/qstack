"""Phase 2 emulator: walks a qstack module and executes it.

This first version handles a single ``qstack.kernel`` and its body:

* Clifford gates (``cliffords.{h,x,y,z,s,cx,cz}``) → ``qsharp.noisy_simulator``
  ``Operation`` applies.
* ``qstack.measure`` → ``sample_instrument`` against a Z-projector;
  post-measure the qubit is reset to ``|0⟩`` and its physical index is
  returned to the free pool.
* ``qstack.return`` → produces the kernel's results (bits + threaded qubits).

``func.call``, ``qstack.select``, ``qstack.invoke``, and ``qstack.decode``
land in Phase 2c.
"""

from __future__ import annotations

import logging
import random
from typing import Any

import numpy as np
from qsharp.noisy_simulator import Instrument, Operation, StateVectorSimulator
from xdsl.dialects.builtin import ModuleOp, SymbolRefAttr
from xdsl.dialects.func import CallOp, FuncOp, ReturnOp as FuncReturnOp
from xdsl.ir import Block, SSAValue

from qstack_mlir.dialect import BitType, QubitType
from qstack_mlir.dialect.core import (
    DecodeOp,
    InvokeOp,
    KernelOp,
    MeasureOp,
    ReturnOp,
    SelectOp,
    UnitaryGateOp,
)
from qstack_mlir.runtime.noise import NoiseChannel, NoiselessChannel
from qstack_mlir.runtime.registry import CallbackRegistry

logger = logging.getLogger("qstack")

_RESET_X_MAT = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=complex)

_Z_INSTRUMENT = Instrument(
    [
        Operation([[[1.0, 0.0], [0.0, 0.0]]]),
        Operation([[[0.0, 0.0], [0.0, 1.0]]]),
    ]
)


# ----------------------------------------------------------------- emulator


class Emulator:
    """Walks qstack IR against a single ``StateVectorSimulator``.

    The simulator has a fixed pool of ``num_qubits`` physical wires; the
    emulator hands out indices from this pool when kernels allocate, and
    returns them when measurements consume.
    """

    def __init__(
        self,
        num_qubits: int,
        *,
        seed: int | None = None,
        module: ModuleOp | None = None,
        registry: CallbackRegistry | None = None,
        noise: NoiseChannel | None = None,
    ) -> None:
        self._num_qubits = num_qubits
        self._rng_seed = seed
        self._module = module
        self._registry = registry
        self._noise: NoiseChannel = noise if noise is not None else NoiselessChannel()
        self._funcs: dict[str, FuncOp] = {}
        if module is not None:
            for op in module.body.ops:
                if isinstance(op, FuncOp):
                    self._funcs[op.sym_name.data] = op
        self._sim: StateVectorSimulator | None = None
        self._free: list[int] = []
        self._env: dict[SSAValue, Any] = {}
        # Cache of (gate_name, dim) -> Operation built with the channel's
        # Kraus matrices composed onto the unitary.
        self._op_cache: dict[tuple[str, int], Operation] = {}

    # ------------------------------------------------------ public API

    def run_kernel(self, kernel: KernelOp) -> list[int | None]:
        """Execute ``kernel`` from a fresh simulator state. Returns its
        results in declaration order: ``int`` for bits, opaque marker for
        qubits (always ``None`` at the top level since qubits never escape
        the outermost kernel)."""
        self._restart()
        results = self._exec_kernel(kernel)
        return self._unbox_values([r.type for r in kernel.results], results)

    def run_func(self, name: str, args: list[Any] | None = None) -> list[int | None]:
        """Execute the module-level ``func.func @name`` from a fresh state.

        ``args`` is the list of values to bind to the entry-block arguments;
        for the top-level driver this is typically empty.
        """
        if name not in self._funcs:
            raise KeyError(f"function @{name} not found in module")
        self._restart()
        fn = self._funcs[name]
        entry = fn.body.blocks[0]
        for arg, value in zip(entry.args, args or []):
            self._env[arg] = value
        returned = self._exec_block(entry)
        return self._unbox_values(list(fn.function_type.outputs.data), returned)

    # ------------------------------------------------------ internals

    def _restart(self) -> None:
        seed = self._rng_seed if self._rng_seed is not None else random.randint(0, 2**31 - 1)
        logger.debug("restart: %s", self._num_qubits)
        self._sim = StateVectorSimulator(self._num_qubits, seed=seed)
        self._free = list(reversed(range(self._num_qubits)))  # pop from end
        self._env = {}

    def _alloc(self) -> int:
        if not self._free:
            raise RuntimeError("emulator out of physical qubits")
        return self._free.pop()

    def _release(self, idx: int) -> None:
        self._free.append(idx)

    def _exec_kernel(self, kernel: KernelOp) -> list[SSAValue]:
        """Run kernel body; return the SSA values listed in qstack.return.

        Captures (outer-scope SSA values referenced by the body) are
        already in ``self._env`` from the enclosing walk.
        """
        body = kernel.body.blocks[0]
        # Allocate one physical wire per entry-block argument.
        for arg in body.args:
            self._env[arg] = self._alloc()
        return self._exec_block(body)

    def _exec_block(self, block: Block) -> list[SSAValue]:
        """Run all ops in `block` in order; return the terminator's
        operand list (as SSA values, so the caller can map them through
        env if needed)."""
        for op in block.ops:
            self._dispatch(op)
            if isinstance(op, (ReturnOp, FuncReturnOp)):
                return list(op.operands)
        raise RuntimeError(f"block did not terminate with a return")

    # ------------------------------------------------------ dispatch

    def _dispatch(self, op) -> None:
        if isinstance(op, UnitaryGateOp):
            self._apply_unitary_op(op)
            return
        if isinstance(op, MeasureOp):
            idx = self._env.pop(op.qubit)
            outcome = self._sim.sample_instrument(_Z_INSTRUMENT, [idx])
            logger.debug("outcome: %s", outcome)
            # Reset to |0⟩ so the wire can be reused.  Reuse the cached
            # (noisy or noiseless) X operation: in the noisy case the reset
            # itself is subject to the same channel, which matches the
            # legacy emulator's behaviour.
            if outcome == 1:
                self._sim.apply_operation(self._gate_op("x", _RESET_X_MAT), [idx])
            self._release(idx)
            self._env[op.result] = int(outcome)
            return
        if isinstance(op, KernelOp):
            # Nested kernel: execute and bind its results into our env.
            saved_env_keys = set(self._env)
            results_ssa = self._exec_kernel(op)
            # Map kernel.results to the values in env keyed by results_ssa.
            for r_out, r_in in zip(op.results, results_ssa):
                self._env[r_out] = self._env[r_in]
                # The inner ReturnOp's operands have served their purpose;
                # transfer ownership to the outer SSA name and clear inner
                # binding so linearity is preserved.
                if r_in not in saved_env_keys:
                    del self._env[r_in]
            return
        if isinstance(op, ReturnOp) or isinstance(op, FuncReturnOp):
            return  # handled by _exec_block
        if isinstance(op, CallOp):
            self._exec_call(op)
            return
        if isinstance(op, SelectOp):
            self._exec_select(op)
            return
        if isinstance(op, InvokeOp):
            self._exec_invoke(op)
            return
        if isinstance(op, DecodeOp):
            self._exec_decode(op)
            return
        raise NotImplementedError(f"emulator: unsupported op {op.name}")

    # ----------------------------------------------------- gate helpers

    def _apply_unitary_op(self, op: UnitaryGateOp) -> None:
        operands = list(op.operands)
        results = list(op.results)
        if len(operands) != len(results):
            raise NotImplementedError(
                f"emulator: gate {op.name} must thread the same number "
                "of operands and results"
            )
        unitary = op.unitary()
        name = self._semantic_cache_key(op)
        if len(operands) == 1:
            self._apply_1q(name, unitary, operands[0], results[0])
            return
        if len(operands) == 2:
            self._apply_2q(name, unitary, operands[0], operands[1], results[0], results[1])
            return
        raise NotImplementedError(
            f"emulator: gate {op.name} has unsupported arity {len(operands)}"
        )

    @staticmethod
    def _semantic_cache_key(op: UnitaryGateOp) -> str:
        values = []
        for name, attr in sorted(op.properties.items()):
            value = getattr(getattr(attr, "value", None), "data", attr)
            values.append((name, value))
        if not values:
            return op.name.rsplit(".", 1)[-1]
        return f"{op.name}{tuple(values)}"

    def _gate_op(self, name: str, unitary: np.ndarray) -> Operation:
        """Return a (cached) ``Operation`` for ``unitary`` under the noise channel."""
        dim = unitary.shape[0]
        key = (name, dim)
        cached = self._op_cache.get(key)
        if cached is not None:
            return cached
        kraus = self._noise.get_kraus_matrices(dim)
        op = Operation([K @ unitary for K in kraus])
        self._op_cache[key] = op
        return op

    def _apply_1q(self, name: str, unitary: np.ndarray, operand: SSAValue, result: SSAValue) -> None:
        idx = self._env.pop(operand)
        logger.debug("eval: %s [%s]", name, idx)
        self._sim.apply_operation(self._gate_op(name, unitary), [idx])
        self._env[result] = idx

    def _apply_2q(
        self,
        name: str,
        unitary: np.ndarray,
        c_in: SSAValue,
        t_in: SSAValue,
        c_out: SSAValue,
        t_out: SSAValue,
    ) -> None:
        c_idx = self._env.pop(c_in)
        t_idx = self._env.pop(t_in)
        # qsharp.noisy_simulator expects qubit list with target first when
        # the operation matrix is written in standard "control ⊗ target"
        # tensor order with little-endian wire indexing. Match the existing
        # qstack emulator convention.
        qubits = [t_idx, c_idx]
        logger.debug("eval: %s %s", name, qubits)
        self._sim.apply_operation(self._gate_op(name, unitary), qubits)
        self._env[c_out] = c_idx
        self._env[t_out] = t_idx

    # ----------------------------------------------------- result unboxing

    def _unbox_values(self, types: list, returned: list[SSAValue]) -> list[int | None]:
        out: list[int | None] = []
        for typ, ssa in zip(types, returned):
            if isinstance(typ, BitType):
                out.append(int(self._env[ssa]))
            elif isinstance(typ, QubitType):
                out.append(None)
            else:  # pragma: no cover
                raise RuntimeError(f"unexpected return type {typ}")
        return out

    # ----------------------------------------------------- call / select / invoke / decode

    def _call_func(self, fn: FuncOp, arg_values: list[Any]) -> list[SSAValue]:
        """Run ``fn`` with ``arg_values`` bound to its entry-block args.

        Returns the SSA values listed in the terminating ``func.return``.
        The values themselves are live in ``self._env``.
        """
        entry = fn.body.blocks[0]
        if len(arg_values) != len(entry.args):
            raise RuntimeError(f"function @{fn.sym_name.data} expects {len(entry.args)} args, got {len(arg_values)}")
        for arg, v in zip(entry.args, arg_values):
            self._env[arg] = v
        return self._exec_block(entry)

    def _exec_call(self, op: CallOp) -> None:
        sym = op.callee.string_value() if hasattr(op.callee, "string_value") else op.callee.root_reference.data
        if sym not in self._funcs:
            raise RuntimeError(f"func.call to unknown symbol @{sym}")
        arg_values = [self._env[a] for a in op.arguments]
        returned = self._call_func(self._funcs[sym], arg_values)
        for out_ssa, ret_ssa in zip(op.results, returned):
            self._env[out_ssa] = self._env[ret_ssa]

    def _exec_select(self, op: SelectOp) -> None:
        if self._registry is None:
            raise RuntimeError("qstack.select requires a CallbackRegistry")
        sym = op.callee.root_reference.data
        fn = self._registry.get_selector(sym)
        kwargs = {name.data: int(self._env[bit]) for name, bit in zip(op.bit_names.data, op.bit_operands)}
        label = fn(**kwargs)
        logger.debug("select: %s %s -> %s", sym, kwargs, label)
        if label not in op.continuations.data:
            raise RuntimeError(
                f"selector @{sym} returned label {label!r} not in menu " f"{list(op.continuations.data)}"
            )
        cont_sym = op.continuations.data[label]
        cont_name = cont_sym.root_reference.data
        if cont_name not in self._funcs:
            raise RuntimeError(f"continuation @{cont_name} not in module")
        # The op's result is the chosen FuncOp itself; qstack.invoke will
        # call it. We park the FuncOp in env keyed by the result SSA value.
        self._env[op.result] = self._funcs[cont_name]

    def _exec_invoke(self, op: InvokeOp) -> None:
        fn = self._env.pop(op.callee)
        if not isinstance(fn, FuncOp):
            raise RuntimeError(f"qstack.invoke target is not a FuncOp: {fn!r}")
        arg_values = [self._env[a] for a in op.args]
        returned = self._call_func(fn, arg_values)
        for out_ssa, ret_ssa in zip(op.results, returned):
            self._env[out_ssa] = self._env[ret_ssa]

    def _exec_decode(self, op: DecodeOp) -> None:
        if self._registry is None:
            raise RuntimeError("qstack.decode requires a CallbackRegistry")
        sym = op.callee.root_reference.data
        fn = self._registry.get_decoder(sym)
        args = [int(self._env[b]) for b in op.bit_operands]
        result = int(fn(*args))
        logger.debug("decode: %s %s -> %s", sym, args, result)
        # Consume the bit operands (single-use).
        for b in op.bit_operands:
            del self._env[b]
        self._env[op.result] = result
