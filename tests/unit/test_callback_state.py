from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import Block, Region

from qstack.dialect import BitType, QubitType
from qstack.dialect.core import DecodeOp, DecoderOp, KernelOp, MeasureOp, ReturnOp
from qstack.runtime import CallbackRegistry, Machine


def _two_decodes(first: DecoderOp, second: DecoderOp) -> ModuleOp:
    block = Block(arg_types=[QubitType(), QubitType()])
    first_measure = MeasureOp(operand=block.args[0])
    second_measure = MeasureOp(operand=block.args[1])
    first_decode = DecodeOp(
        callee=first.sym_name.data, bit_operands=[first_measure.result]
    )
    second_decode = DecodeOp(
        callee=second.sym_name.data, bit_operands=[second_measure.result]
    )
    block.add_ops([first_measure, second_measure, first_decode, second_decode])
    block.add_op(ReturnOp(operands=[first_decode.result, second_decode.result]))
    main = KernelOp(
        "main",
        input_types=[],
        result_types=[BitType(), BitType()],
        allocates=2,
        region=Region([block]),
    )
    return ModuleOp([first, second, main])


def test_callbacks_share_context_within_a_source_and_reset_between_shots() -> None:
    module = _two_decodes(
        DecoderOp("feedback.1:first", 1),
        DecoderOp("feedback.1:second", 1),
    )
    registry = CallbackRegistry()
    contexts = []

    @registry.decoder("feedback:first", stateful=True)
    def first(bits, context):
        contexts.append(context)
        context["calls"] = context.get("calls", 0) + 1
        return context["calls"]

    @registry.decoder("feedback:second", stateful=True)
    def second(bits, context):
        contexts.append(context)
        context["calls"] += 1
        return context["calls"] - 1

    machine = Machine(num_qubits=2, registry=registry)
    assert machine.single_shot(module) == [1, 1]
    assert machine.single_shot(module) == [1, 1]
    assert contexts[0] is contexts[1]
    assert contexts[2] is contexts[3]
    assert contexts[0] is not contexts[2]


def test_callback_layers_have_separate_contexts() -> None:
    module = _two_decodes(
        DecoderOp("feedback.1:decode", 1),
        DecoderOp("feedback.2:decode", 1),
    )
    registry = CallbackRegistry()
    contexts = []

    @registry.decoder("feedback:decode", stateful=True)
    def decode(bits, context):
        contexts.append(context)
        context["calls"] = context.get("calls", 0) + 1
        return context["calls"]

    assert Machine(num_qubits=2, registry=registry).single_shot(module) == [1, 1]
    assert contexts[0] is not contexts[1]
