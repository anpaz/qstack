"""Lower QSTACKQASM 0.1 directly to the kernel-only qstack IR.

The surface grammar is intentionally unchanged.  This lowering only changes
its target: definitions, generated switch cases, and the synthesized program
entry are all named ``qstack.kernel`` symbols.

Every qubit parameter a ``def`` (or a generated switch-case kernel) declares
is returned, unconditionally, in declaration order -- there is no inference
of which parameters "survive" a body.  Measuring a qubit that must be
returned implicitly substitutes a fresh ``|0>`` in its place, realized as one
more entry in the kernel's ``allocates`` count; measuring anything else (a
local ancilla) simply consumes it.  Every qubit and bit that comes into
existence in a body must be consumed by something before the body's
``qstack.return`` -- an unconsumed local ancilla or bit is a compile error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from lark import Token, Tree
from xdsl.dialects.builtin import Float64Type, FloatAttr, ModuleOp, SymbolRefAttr
from xdsl.ir import Block, Operation, Region, SSAValue

from qstack.dialect import BitType, QubitType
from qstack.dialect.core import (
    CallOp,
    DecoderOp,
    KernelOp,
    MeasureOp,
    ReturnOp,
    SelectOp,
    SelectorOp,
)
from qstack.surface.isa_includes import IncludeGateSet, resolve_includes


def _is_tree(node: object, *names: str) -> bool:
    return isinstance(node, Tree) and node.data in names


def _qubit_arg_name(node: Tree) -> str:
    if node.data == "qubit_ref":
        return str(node.children[0])
    if node.data == "qubit_index":
        return f"{node.children[0]}[{node.children[1]}]"
    raise NotImplementedError(f"unsupported qubit reference {node.data!r}")


def _bit_target_name(node: Tree) -> str:
    if node.data == "bit_ref":
        return str(node.children[0])
    if node.data == "bit_index":
        return f"{node.children[0]}[{node.children[1]}]"
    raise NotImplementedError(f"unsupported bit reference {node.data!r}")


def _block_stmts(block: Tree) -> list[Tree]:
    return [child for child in block.children if isinstance(child, Tree)]


def _referenced_qubit_names(node: Tree) -> set[str]:
    """Every qubit name referenced anywhere under ``node``, including inside
    nested switch-case blocks.  A ``qreg`` element that never appears here is
    never allocated -- it never entered the IR, so it needs no disposition.
    """

    names: set[str] = set()
    for child in node.children:
        if not isinstance(child, Tree):
            continue
        if child.data in ("qubit_ref", "qubit_index"):
            names.add(_qubit_arg_name(child))
        else:
            names |= _referenced_qubit_names(child)
    return names


@dataclass
class _Env:
    qubits: dict[str, SSAValue] = field(default_factory=dict)
    bits: dict[str, SSAValue] = field(default_factory=dict)
    qubit_order: list[str] = field(default_factory=list)
    # Names that must still be bound to a live qubit when this scope ends:
    # a def's parameters, or (for a switch-case kernel) every qubit threaded
    # through the switch.  Measuring one of these substitutes a fresh |0>
    # instead of retiring the name.
    replace_on_measure: frozenset[str] = field(default_factory=frozenset)

    def add_qubit(self, name: str, value: SSAValue) -> None:
        if name not in self.qubits:
            self.qubit_order.append(name)
        self.qubits[name] = value

    def drop_qubit(self, name: str) -> None:
        self.qubits.pop(name)
        self.qubit_order.remove(name)


class _AllocCursor:
    """Grows a kernel's ``allocates`` count on demand.

    A measured qubit that must be replaced (``_Env.replace_on_measure``)
    needs one more fresh ``|0>`` than the body's own ``qreg`` declarations
    accounted for. Rather than pre-scanning a body to size the block up
    front, allocations are appended to the block as they're needed, always
    ahead of the borrowed/threaded parameters that follow them.
    """

    def __init__(self, block: Block, count: int) -> None:
        self._block = block
        self.count = count

    def fresh_qubit(self) -> SSAValue:
        argument = self._block.insert_arg(QubitType(), self.count)
        self.count += 1
        return argument


@dataclass(frozen=True)
class _KernelDecl:
    inputs: tuple[object, ...]
    results: tuple[object, ...]


class _Lower:
    def __init__(self) -> None:
        self.module = ModuleOp([])
        self.include_gates = IncludeGateSet(includes=(), gates={})
        self.kernels: dict[str, _KernelDecl] = {}
        self.selector_arity: dict[str, int] = {}
        self.case_counter = 0

    def lower(self, tree: Tree) -> ModuleOp:
        if tree.data != "start":
            raise ValueError(f"expected a start tree, got {tree.data!r}")
        self.include_gates = resolve_includes([child for child in tree.children if _is_tree(child, "include")])

        definitions = [child for child in tree.children if _is_tree(child, "def_decl")]
        for definition in definitions:
            name, params = self._def_signature(definition)
            if any(kind != "qubit_type" for kind, _ in params):
                raise NotImplementedError(f"def @{name}: only qubit parameters are supported")
            # Every qubit parameter is returned, unconditionally, in
            # parameter order: a def's signature is symmetric in qubits.
            qubit_types = tuple(QubitType() for _ in params)
            self.kernels[name] = _KernelDecl(qubit_types, qubit_types)

        for child in tree.children:
            if _is_tree(child, "extern_decl"):
                self._build_extern(child, selector=False)
            elif _is_tree(child, "selector_decl"):
                self._build_extern(child, selector=True)

        for definition in definitions:
            self._build_definition(definition)

        top_stmts = [
            child
            for child in tree.children
            if _is_tree(child, "qreg_stmt", "creg_stmt", "apply_stmt", "measure_stmt")
        ]
        if top_stmts:
            self._build_main(top_stmts)
        return self.module

    def _build_extern(self, node: Tree, *, selector: bool) -> None:
        name = str(node.children[0])
        types = list(node.children[1].children)
        if any(typ.data != "bit_type" for typ in types):
            raise NotImplementedError(f"callback @{name}: only bit inputs are supported")
        arity = len(types)
        if selector:
            self.selector_arity[name] = arity
            self.module.body.block.add_op(SelectorOp(name, arity))
            return
        result = node.children[2]
        if result.data != "bit_type":
            raise NotImplementedError(f"decoder @{name}: result must be bit")
        self.module.body.block.add_op(DecoderOp(name, arity))

    def _def_signature(self, node: Tree) -> tuple[str, list[tuple[str, str]]]:
        name = str(node.children[0])
        params: list[tuple[str, str]] = []
        for child in node.children[1:]:
            if _is_tree(child, "param_list"):
                for parameter in child.children:
                    params.append((parameter.children[0].data, str(parameter.children[1])))
        return name, params

    def _build_definition(self, node: Tree) -> None:
        name, params = self._def_signature(node)
        parameter_names = [parameter for _, parameter in params]
        body = next(child for child in node.children if _is_tree(child, "block"))
        statements = _block_stmts(body)
        referenced = _referenced_qubit_names(body)
        alloc_names = [n for n in self._allocation_names(statements) if n in referenced]

        input_types = [QubitType() for _ in params]
        block = Block(arg_types=[*[QubitType() for _ in alloc_names], *input_types])
        allocs = _AllocCursor(block, len(alloc_names))
        env = _Env(replace_on_measure=frozenset(parameter_names))
        for value, alloc_name in zip(block.args[: len(alloc_names)], alloc_names, strict=True):
            env.add_qubit(alloc_name, value)
        for (_, parameter), value in zip(params, block.args[len(alloc_names) :], strict=True):
            env.add_qubit(parameter, value)

        self._lower_statements(statements, block, env, allocs)

        leftover = [n for n in env.qubit_order if n not in parameter_names]
        if leftover:
            raise ValueError(
                f"def @{name}: local qubit(s) {', '.join(leftover)} must be measured "
                "before the end of the body"
            )
        if env.bits:
            raise ValueError(f"def @{name}: bit(s) {', '.join(env.bits)} were measured but never consumed")

        outputs = [env.qubits[parameter] for parameter in parameter_names]
        block.add_op(ReturnOp(operands=outputs))
        declared = self.kernels[name]
        self.module.body.block.add_op(
            KernelOp(
                name,
                input_types=declared.inputs,
                result_types=declared.results,
                allocates=allocs.count,
                region=Region([block]),
            )
        )

    def _build_main(self, statements: list[Tree]) -> None:
        referenced: set[str] = set()
        for statement in statements:
            referenced |= _referenced_qubit_names(statement)
        alloc_names = [n for n in self._allocation_names(statements) if n in referenced]
        block = Block(arg_types=[QubitType() for _ in alloc_names])
        allocs = _AllocCursor(block, len(alloc_names))
        env = _Env()
        for value, name in zip(block.args, alloc_names, strict=True):
            env.add_qubit(name, value)
        self._lower_statements(statements, block, env, allocs)
        if env.qubit_order:
            raise ValueError(
                f"main: qubit(s) {', '.join(env.qubit_order)} must be measured before the program ends"
            )
        outputs = list(env.bits.values())
        block.add_op(ReturnOp(operands=outputs))
        main = KernelOp(
            "main",
            input_types=[],
            result_types=[BitType() for _ in outputs],
            allocates=allocs.count,
            region=Region([block]),
        )
        self.kernels["main"] = _KernelDecl((), tuple(main.declared_result_types))
        self.module.body.block.add_op(main)

    @staticmethod
    def _allocation_names(statements: Iterable[Tree]) -> list[str]:
        names: list[str] = []
        for statement in statements:
            if statement.data != "qreg_stmt":
                continue
            register = str(statement.children[0])
            count = int(statement.children[1])
            names.extend(f"{register}[{index}]" for index in range(count))
        return names

    def _lower_statements(self, statements: Iterable[Tree], block: Block, env: _Env, allocs: _AllocCursor) -> None:
        for statement in statements:
            if statement.data in {"qreg_stmt", "creg_stmt", "bit_stmt"}:
                continue
            if statement.data == "apply_stmt":
                self._lower_apply(statement, block, env)
            elif statement.data == "measure_stmt":
                self._lower_measure(statement, block, env, allocs)
            elif statement.data == "switch_stmt":
                self._lower_switch(statement, block, env)
            else:
                raise NotImplementedError(f"unsupported statement {statement.data!r}")

    def _lower_apply(self, statement: Tree, block: Block, env: _Env) -> None:
        name = str(statement.children[0])
        rest = list(statement.children[1:])
        params: list[float] = []
        if rest and _is_tree(rest[0], "gate_params"):
            params = [float(item.children[0]) for item in rest[0].children if _is_tree(item, "gate_param")]
            rest = rest[1:]
        arg_names = [_qubit_arg_name(item) for item in rest if isinstance(item, Tree)]
        operands = [env.qubits[arg] for arg in arg_names]
        if name in self.kernels:
            if params:
                raise ValueError(f"kernel @{name} does not accept gate parameters")
            signature = self.kernels[name]
            call = CallOp(name, operands, signature.results)
            block.add_op(call)
            # Every argument comes back, in order: a call is opaque, and the
            # caller cannot tell -- and is not told -- which of its returned
            # qubits are physically fresh |0>s substituted by the callee.
            for arg_name, result in zip(arg_names, call.results, strict=True):
                env.qubits[arg_name] = result
            return
        if name not in self.include_gates.gates:
            raise NotImplementedError(f"unknown apply target {name!r}")
        declaration = self.include_gates.gates[name]
        if len(params) != len(declaration.params):
            raise ValueError(f"gate {name!r} expects {len(declaration.params)} parameters, got {len(params)}")
        if len(operands) != declaration.arity:
            raise ValueError(f"gate {name!r} expects {declaration.arity} qubits, got {len(operands)}")
        properties = {
            parameter: FloatAttr(float(value), Float64Type())
            for parameter, value in zip(declaration.params, params, strict=True)
        }
        gate: Operation = declaration.op_type.create(
            operands=operands,
            result_types=[QubitType() for _ in operands],
            properties=properties,
        )
        block.add_op(gate)
        for arg_name, result in zip(arg_names, gate.results, strict=True):
            env.qubits[arg_name] = result

    def _lower_measure(self, statement: Tree, block: Block, env: _Env, allocs: _AllocCursor) -> None:
        qubit_name = _qubit_arg_name(statement.children[0])
        bit_name = _bit_target_name(statement.children[1])
        measure = MeasureOp(operand=env.qubits[qubit_name])
        block.add_op(measure)
        if qubit_name in env.replace_on_measure:
            # Z-measurement plus reset: the name must still be live when
            # this scope returns, so it's rebound to a freshly prepared |0>.
            env.qubits[qubit_name] = allocs.fresh_qubit()
        else:
            env.drop_qubit(qubit_name)
        env.bits[bit_name] = measure.result

    def _lower_switch(self, statement: Tree, block: Block, env: _Env) -> None:
        call = statement.children[0]
        selector_name = str(call.children[0])
        try:
            declared_arity = self.selector_arity[selector_name]
        except KeyError as exc:
            raise ValueError(f"unknown selector @{selector_name}") from exc
        bit_args = call.children[1] if len(call.children) > 1 else None
        bit_refs = [item for item in bit_args.children if isinstance(item, Tree)] if bit_args else []
        if len(bit_refs) != declared_arity:
            raise ValueError(f"selector @{selector_name} expects {declared_arity} bits, got {len(bit_refs)}")
        bit_values = [env.bits[_bit_target_name(item)] for item in bit_refs]
        live_names = list(env.qubit_order)
        case_arguments = [env.qubits[name] for name in live_names]
        case_types = [value.type for value in case_arguments]
        cases: dict[str, SymbolRefAttr] = {}
        for arm in [child for child in statement.children[1:] if _is_tree(child, "case_arm")]:
            label = str(arm.children[0])
            cases[label] = SymbolRefAttr(self._emit_case_kernel(label, arm.children[1], live_names))
        select = SelectOp(
            callee=selector_name,
            bit_operands=bit_values,
            cases=cases,
            case_arguments=case_arguments,
            result_types=case_types,
        )
        block.add_op(select)
        for bit in bit_refs:
            env.bits.pop(_bit_target_name(bit))
        for name, result in zip(live_names, select.results, strict=True):
            env.qubits[name] = result

    def _emit_case_kernel(self, label: str, case_block: Tree, live_names: list[str]) -> str:
        self.case_counter += 1
        name = f"__qstack_case_{label}_{self.case_counter}"
        inputs = [QubitType() for _ in live_names]
        block = Block(arg_types=inputs)
        allocs = _AllocCursor(block, 0)
        # Every qubit threaded through a switch must come back out of each
        # case, exactly like a def's parameters (§4.6): a case kernel's
        # "parameters" are the full set of qubits live at the switch.
        env = _Env(replace_on_measure=frozenset(live_names))
        for live_name, value in zip(live_names, block.args, strict=True):
            env.add_qubit(live_name, value)
        statements = _block_stmts(case_block)
        if any(statement.data == "qreg_stmt" for statement in statements):
            raise NotImplementedError("qreg declarations inside switch cases are not supported")
        self._lower_statements(statements, block, env, allocs)
        if env.bits:
            raise ValueError(f"case {label!r}: bit(s) {', '.join(env.bits)} were measured but never consumed")
        outputs = [env.qubits[live_name] for live_name in live_names]
        block.add_op(ReturnOp(operands=outputs))
        self.kernels[name] = _KernelDecl(tuple(inputs), tuple(inputs))
        self.module.body.block.add_op(
            KernelOp(name, input_types=inputs, result_types=inputs, allocates=allocs.count, region=Region([block]))
        )
        return name


def lower(tree: Tree) -> ModuleOp:
    return _Lower().lower(tree)
