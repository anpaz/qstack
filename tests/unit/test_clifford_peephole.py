import numpy as np
import pytest
from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.cliffords import HOp, SOp, XOp, YOp, ZOp
from qstack.dialect.core import KernelOp, MeasureOp, ReturnOp
from qstack.passes.clifford_peephole import (
    CliffordPeepholeOptimization,
    optimize_cliffords,
)
from qstack.verifier import verify_module


def _module(gates):
    block = Block(arg_types=[QubitType()])
    value = block.args[0]
    for gate_type in gates:
        gate = gate_type(value)
        block.add_op(gate)
        value = gate.result
    measure = MeasureOp(operand=value)
    block.add_op(measure)
    block.add_op(ReturnOp(operands=[measure.result]))
    return ModuleOp(
        [
            KernelOp(
                "main",
                input_types=[],
                result_types=[BitType()],
                allocates=1,
                region=Region([block]),
            )
        ]
    )


def _gates(module):
    return [
        op
        for op in module.walk()
        if isinstance(op, (HOp, SOp, XOp, YOp, ZOp))
    ]


def test_clifford_peephole_rules() -> None:
    for gate_type in (HOp, XOp, YOp, ZOp):
        source = _module([gate_type, gate_type])
        target = optimize_cliffords(source)
        verify_module(source)
        verify_module(target)
        assert _gates(target) == []
        assert len(_gates(source)) == 2

    target = optimize_cliffords(_module([SOp, SOp]))
    assert [type(op) for op in _gates(target)] == [ZOp]


def test_clifford_peephole_is_one_non_overlapping_sweep() -> None:
    first = optimize_cliffords(_module([SOp, SOp, SOp, SOp]))
    assert [type(op) for op in _gates(first)] == [ZOp, ZOp]
    second = optimize_cliffords(first)
    assert _gates(second) == []


def test_clifford_peephole_does_not_cross_an_intervening_operation() -> None:
    target = optimize_cliffords(_module([HOp, XOp, HOp]))
    assert [type(op) for op in _gates(target)] == [HOp, XOp, HOp]


def test_same_gates_on_different_wires_do_not_match() -> None:
    block = Block(arg_types=[QubitType(), QubitType()])
    first = HOp(block.args[0])
    second = HOp(block.args[1])
    block.add_ops([first, second])
    first_measure = MeasureOp(operand=first.result)
    second_measure = MeasureOp(operand=second.result)
    block.add_ops([first_measure, second_measure])
    block.add_op(ReturnOp(operands=[first_measure.result, second_measure.result]))
    module = ModuleOp(
        [
            KernelOp(
                "main",
                input_types=[],
                result_types=[BitType(), BitType()],
                allocates=2,
                region=Region([block]),
            )
        ]
    )
    assert [type(op) for op in _gates(optimize_cliffords(module))] == [HOp, HOp]


def test_clifford_rule_matrices_are_exact_up_to_global_phase() -> None:
    identity = np.eye(2)
    for gate_type in (HOp, XOp, YOp, ZOp):
        block = Block(arg_types=[QubitType()])
        gate = gate_type(block.args[0])
        assert np.allclose(gate.unitary() @ gate.unitary(), identity)
    block = Block(arg_types=[QubitType()])
    s = SOp(block.args[0])
    z = ZOp(block.args[0])
    assert np.allclose(s.unitary() @ s.unitary(), z.unitary())


def test_optimization_instance_can_be_reused() -> None:
    optimization = CliffordPeepholeOptimization()
    first = optimization.run(_module([HOp, HOp]))
    second = optimization.run(_module([SOp, SOp]))
    assert _gates(first) == []
    assert [type(op) for op in _gates(second)] == [ZOp]


@pytest.mark.parametrize("gate_type", [HOp, SOp])
def test_optimization_records_source_pair_and_escaping_boundary(gate_type) -> None:
    class RecordingOptimization(CliffordPeepholeOptimization):
        def lower_body(self, operations, inputs, context):
            self.replacements = super().lower_body(operations, inputs, context)
            return self.replacements

    source = _module([gate_type, gate_type, XOp])
    source_main = next(op for op in source.body.ops if isinstance(op, KernelOp))
    source_ops = tuple(source_main.body.block.ops)
    source_values = (*source_main.body.block.args, *(v for op in source_ops for v in op.results))
    uses_before = {v: tuple(v.uses) for v in source_values}
    optimization = RecordingOptimization()
    target = optimization.run(source)
    target_main = next(op for op in target.body.ops if isinstance(op, KernelOp))
    pair, following, measure, returned = optimization.replacements

    assert pair.source_operations == source_ops[:2]
    assert pair.inputs == ((source_main.body.block.args[0], target_main.body.block.args[0]),)
    assert pair.outputs[0][0] is source_ops[1].results[0]
    if gate_type is HOp:
        assert pair.target_operations == ()
        assert pair.outputs[0][1] is target_main.body.block.args[0]
    else:
        assert len(pair.target_operations) == 1
        assert isinstance(pair.target_operations[0], ZOp)
        assert pair.outputs[0][1] is pair.target_operations[0].result
    assert following.inputs == pair.outputs
    assert measure.inputs == following.outputs
    assert returned.inputs == measure.outputs
    assert all(tuple(value.uses) == uses_before[value] for value in source_values)
    assert not (set(source_values) & {value for op in target.walk() for value in op.operands})
