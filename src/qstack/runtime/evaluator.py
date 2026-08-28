"""Kernel-only qstack module evaluator."""

from __future__ import annotations

from typing import Any

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Block, SSAValue

from qstack.dialect import BitType
from qstack.dialect.core import CallOp, DecodeOp, KernelOp, MeasureOp, ReturnOp, SelectOp, UnitaryGateOp
from qstack.runtime.cpu import CPU
from qstack.runtime.noise import NoiseChannel
from qstack.runtime.qpu import GateApplication, QPU, QPUProtocol
from qstack.runtime.registry import CallbackRegistry
from qstack.verifier import verify_module


class ModuleEvaluator:
    """Execute a verified named-kernel module against a QPU and CPU."""

    def __init__(
        self,
        num_qubits: int,
        *,
        module: ModuleOp,
        seed: int | None = None,
        registry: CallbackRegistry | None = None,
        noise: NoiseChannel | None = None,
        qpu: QPUProtocol | None = None,
        cpu: CPU | None = None,
    ) -> None:
        verify_module(module)
        self._module = module
        self._qpu = qpu if qpu is not None else QPU(num_qubits, seed=seed, noise=noise)
        self._cpu = cpu if cpu is not None else CPU(registry)
        self._kernels = {
            op.sym_name.data: op
            for op in module.body.ops
            if isinstance(op, KernelOp)
        }

    def run_main(self) -> list[int]:
        """Run ``qstack.kernel @main`` from fresh quantum/classical state."""
        self._cpu.restart()
        self._qpu.restart()
        main = self._kernels["main"]
        values = self._exec_kernel(main, [])
        return [int(value) for value in values]

    def _exec_kernel(self, kernel: KernelOp, arguments: list[Any]) -> list[Any]:
        if len(arguments) != len(kernel.input_types):
            raise RuntimeError(
                f"kernel @{kernel.sym_name.data} expects {len(kernel.input_types)} arguments, got {len(arguments)}"
            )
        block = kernel.body.blocks[0]
        env: dict[SSAValue, Any] = {}
        for value, argument in zip(block.args[: len(arguments)], arguments, strict=True):
            env[value] = argument
        for value in block.args[len(arguments) :]:
            env[value] = self._qpu.allocate()
        return self._exec_block(block, env)

    def _exec_block(self, block: Block, env: dict[SSAValue, Any]) -> list[Any]:
        for op in block.ops:
            if isinstance(op, ReturnOp):
                return [env.pop(value) for value in op.operands]
            self._dispatch(op, env)
        raise RuntimeError("kernel block did not terminate with qstack.return")

    def _dispatch(self, op, env: dict[SSAValue, Any]) -> None:
        if isinstance(op, UnitaryGateOp):
            self._apply_gate(op, env)
            return
        if isinstance(op, MeasureOp):
            env[op.result] = self._qpu.measure(env.pop(op.qubit))
            return
        if isinstance(op, CallOp):
            kernel = self._kernels[op.callee.root_reference.data]
            values = self._exec_kernel(kernel, [env.pop(value) for value in op.arguments])
            for result, value in zip(op.results, values, strict=True):
                env[result] = value
            return
        if isinstance(op, DecodeOp):
            bits = tuple(int(env.pop(value)) for value in op.bit_operands)
            env[op.result] = self._cpu.decode(op, bits)
            return
        if isinstance(op, SelectOp):
            bits = tuple(int(env.pop(value)) for value in op.bit_operands)
            label = self._cpu.select(op, bits)
            target = op.cases.data[label].root_reference.data
            values = self._exec_kernel(self._kernels[target], [env.pop(value) for value in op.case_arguments])
            for result, value in zip(op.results, values, strict=True):
                env[result] = value
            return
        raise NotImplementedError(f"evaluator: unsupported operation {op.name}")

    def _apply_gate(self, op: UnitaryGateOp, env: dict[SSAValue, Any]) -> None:
        operands = list(op.operands)
        results = list(op.results)
        if len(operands) != len(results):
            raise RuntimeError(f"evaluator: gate {op.name} must thread one result per operand")
        qubits = tuple(env.pop(value) for value in operands)
        if len(qubits) not in {1, 2}:
            raise NotImplementedError(f"evaluator: gate {op.name} has unsupported arity {len(qubits)}")
        self._qpu.apply_gate(GateApplication(op=op, qubits=qubits))
        for result, qubit in zip(results, qubits, strict=True):
            env[result] = qubit
