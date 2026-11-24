"""Lower QSTACKQASM 0.1 directly to the kernel-only qstack IR.

Definitions, generated switch-case and loop kernels, and the synthesized
program entry are all named ``qstack.kernel`` symbols.

Qubits
------
A qubit is allocated, in ``|0>``, where it is declared, if the program uses
it; one that is never used never enters the IR.
``measure q -> c`` consumes the value of ``q``.  If the name ``q`` is used
again later in the kernel being built, or the kernel must return it, the
name is bound at once to a newly allocated ``|0>``: a measurement followed by
a reset.  Otherwise the name is retired.

Kernels
-------
* A ``def`` borrows its qubit parameters and returns every one of them, in
  parameter order.
* Each ``switch`` arm becomes a case kernel that borrows the qubits live at
  the switch and returns them, exactly like a ``def``.
* ``while (s(bits)) { body }`` becomes a loop kernel and an exit kernel, both
  borrowing the qubits live at the loop.  A select at the loop runs the loop
  kernel on label ``"1"`` and the exit kernel on ``"0"``; the loop kernel
  runs the body and ends in the same select.  The body must measure every
  bit the condition reads.
* ``for`` loops have compile-time bounds and are unrolled before lowering,
  one block per iteration, with the loop variable replaced by its value.
* The top-level statements form ``@main``, which returns the bits that are
  still unread when it ends.

Every qubit a block declares must be measured before the block ends, and
every bit measured in a kernel other than ``@main`` must be read before it
ends.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from lark import Token, Tree
from xdsl.dialects.builtin import Float64Type, FloatAttr, ModuleOp, SymbolRefAttr
from xdsl.ir import Block, Operation, Region, SSAValue

from qstack.dialect import BitType, QubitType
from qstack.dialect.core import (
    CallOp,
    DecodeOp,
    DecoderOp,
    KernelOp,
    MeasureOp,
    ReturnOp,
    SelectOp,
    SelectorOp,
)
from qstack.surface.isa_includes import IncludeGateSet, resolve_includes

# A while loop's selector returns this label to run the body again ...
WHILE_CONTINUE = "1"
# ... and this one to leave the loop.
WHILE_EXIT = "0"

_STATEMENTS = frozenset(
    {
        "qubit_stmt",
        "bit_stmt",
        "apply_stmt",
        "call_stmt",
        "measure_stmt",
        "decode_decl",
        "decode_assign",
        "switch_stmt",
        "while_stmt",
        "scope",
    }
)

# The declaration depth of a name a kernel borrows: visible in every block.
_BORROWED = -1


def _is_tree(node: object, *names: str) -> bool:
    return isinstance(node, Tree) and node.data in names


def _block_stmts(block: Tree) -> list[Tree]:
    return [child for child in block.children if isinstance(child, Tree)]


def _integer(token: Token, what: str) -> int:
    text = str(token)
    if not text.isdigit():
        raise ValueError(f"{what} must be a non-negative integer, got {text!r}")
    return int(text)


# ----------------------------------------------------------------------
# for-loop unrolling: a source-to-source step before lowering


def _loop_values(node: Tree) -> list[int]:
    numbers = [_integer(token, "a for-loop bound") for token in node.children]
    if node.data == "range2":
        start, stop = numbers
        return list(range(start, stop + 1))
    if node.data == "range3":
        start, step, stop = numbers
        if step == 0:
            raise ValueError("a for-loop step must be positive")
        return list(range(start, stop + 1, step))
    return numbers


def _substitute(node: object, variable: str, value: int) -> object:
    """A copy of ``node`` with every index ``variable`` replaced by ``value``."""
    if not isinstance(node, Tree):
        return node
    if node.data == "for_stmt" and str(node.children[1]) == variable:
        raise ValueError(f"for-loop variable {variable} is already in use")
    if node.data == "index":
        token = node.children[0]
        if token.type == "IDENT" and str(token) == variable:
            return Tree("index", [Token("NUMBER", str(value))])
        return node
    return Tree(node.data, [_substitute(child, variable, value) for child in node.children], node.meta)


def _unroll(node: object) -> object:
    """Replace every ``for`` statement with one ``scope`` block per iteration."""
    if not isinstance(node, Tree):
        return node
    children: list[object] = []
    for child in node.children:
        if _is_tree(child, "for_stmt"):
            _, variable, values, body = child.children
            for value in _loop_values(values):
                iteration = _unroll(_substitute(copy.deepcopy(body), str(variable), value))
                children.append(Tree("scope", list(iteration.children)))
        else:
            children.append(_unroll(child))
    return Tree(node.data, children, node.meta)


# ----------------------------------------------------------------------


class _AllocCursor:
    """Grows a kernel's ``allocates`` count on demand.

    Fresh qubits are block arguments placed ahead of the borrowed ones, so
    each allocation is inserted at the current count.
    """

    def __init__(self, block: Block, count: int) -> None:
        self._block = block
        self.count = count

    def fresh_qubit(self) -> SSAValue:
        argument = self._block.insert_arg(QubitType(), self.count)
        self.count += 1
        return argument


@dataclass
class _Frame:
    """One kernel under construction."""

    where: str
    block: Block
    allocs: _AllocCursor
    # The value that currently holds each live qubit name, in the order the
    # names came into scope.
    qubits: dict[str, SSAValue]
    # The names this kernel borrows and must return, in order.
    borrowed: list[str]
    # Every qubit name in scope, live or not, with the depth of the block
    # that declares it.
    declared: dict[str, int]
    # Bits measured or decoded here and not yet read.
    bits: dict[str, SSAValue] = field(default_factory=dict)
    # For each enclosing block of this kernel, innermost last: the qubit
    # names it declares, and the statements that remain in it.
    scopes: list[list[str]] = field(default_factory=list)
    remaining: list[list[Tree]] = field(default_factory=list)
    # Names whose current value came back from a select.
    from_select: set[str] = field(default_factory=set)

    def value(self, name: str) -> SSAValue:
        if name not in self.qubits:
            raise ValueError(f"{self.where}: unknown qubit {name}")
        return self.qubits[name]

    def bind(self, name: str, value: SSAValue) -> None:
        self.qubits[name] = value
        self.from_select.discard(name)

    def read_bit(self, name: str) -> SSAValue:
        try:
            return self.bits.pop(name)
        except KeyError:
            raise ValueError(
                f"{self.where}: bit {name} has no unread value here; a bit is read "
                "once, in the kernel that measures it"
            ) from None


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
        self.selector_result: dict[str, str] = {}
        self.decoder_arity: dict[str, int] = {}
        self.case_counter = 0
        self.loop_counter = 0
        self._references: dict[int, frozenset[str]] = {}

    def lower(self, tree: Tree) -> ModuleOp:
        if tree.data != "start":
            raise ValueError(f"expected a start tree, got {tree.data!r}")
        tree = _unroll(tree)
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

        top_stmts = [child for child in tree.children if isinstance(child, Tree) and child.data in _STATEMENTS]
        if top_stmts:
            self._build_main(top_stmts)
        return self.module

    # ------------------------------------------------------------------
    # declarations and kernels

    def _build_extern(self, node: Tree, *, selector: bool) -> None:
        name = str(node.children[0])
        types = list(node.children[1].children)
        if any(typ.data != "bit_type" for typ in types):
            raise NotImplementedError(f"callback @{name}: only bit inputs are supported")
        arity = len(types)
        result = node.children[2]
        if selector:
            if result.data not in {"int_type", "bool_type"}:
                raise NotImplementedError(f"selector @{name}: result must be int or bool")
            self.selector_arity[name] = arity
            self.selector_result[name] = str(result.data).removesuffix("_type")
            self.module.body.block.add_op(SelectorOp(name, arity))
            return
        if result.data != "bit_type":
            raise NotImplementedError(f"decoder @{name}: result must be bit")
        self.decoder_arity[name] = arity
        self.module.body.block.add_op(DecoderOp(name, arity))

    def _def_signature(self, node: Tree) -> tuple[str, list[tuple[str, str]]]:
        name = str(node.children[0])
        params: list[tuple[str, str]] = []
        for child in node.children[1:]:
            if _is_tree(child, "param_list"):
                for parameter in child.children:
                    params.append((parameter.children[0].data, str(parameter.children[1])))
        return name, params

    @staticmethod
    def _frame(where: str, borrowed: list[str]) -> _Frame:
        block = Block(arg_types=[QubitType() for _ in borrowed])
        return _Frame(
            where=where,
            block=block,
            allocs=_AllocCursor(block, 0),
            qubits=dict(zip(borrowed, block.args, strict=True)),
            borrowed=list(borrowed),
            declared={name: _BORROWED for name in borrowed},
        )

    @staticmethod
    def _finish(frame: _Frame) -> list[SSAValue]:
        """Check that every bit was read, and return the borrowed names' values."""
        if frame.bits:
            raise ValueError(f"{frame.where}: bit(s) {', '.join(frame.bits)} were measured but never consumed")
        return [frame.value(name) for name in frame.borrowed]

    def _add_kernel(self, name: str, frame: _Frame, results: list[object]) -> None:
        inputs = [QubitType() for _ in frame.borrowed]
        self.module.body.block.add_op(
            KernelOp(
                name,
                input_types=inputs,
                result_types=results,
                allocates=frame.allocs.count,
                region=Region([frame.block]),
            )
        )

    def _build_definition(self, node: Tree) -> None:
        name, params = self._def_signature(node)
        body = next(child for child in node.children if _is_tree(child, "block"))
        frame = self._frame(f"def @{name}", [parameter for _, parameter in params])
        self._lower_block(_block_stmts(body), frame)
        outputs = self._finish(frame)
        frame.block.add_op(ReturnOp(operands=outputs))
        self._add_kernel(name, frame, list(self.kernels[name].results))

    def _build_main(self, statements: list[Tree]) -> None:
        frame = self._frame("main", [])
        self._lower_block(statements, frame, end="before the program ends")
        outputs = list(frame.bits.values())
        frame.block.add_op(ReturnOp(operands=outputs))
        results = [BitType() for _ in outputs]
        self.kernels["main"] = _KernelDecl((), tuple(results))
        self._add_kernel("main", frame, results)

    def _generated_kernel(self, name: str, where: str, statements: list[Tree], borrowed: list[str]) -> None:
        """A kernel that borrows ``borrowed``, runs ``statements`` and returns them."""
        frame = self._frame(where, borrowed)
        self._lower_block(statements, frame)
        outputs = self._finish(frame)
        frame.block.add_op(ReturnOp(operands=outputs))
        types = tuple(QubitType() for _ in borrowed)
        self.kernels[name] = _KernelDecl(types, types)
        self._add_kernel(name, frame, list(types))

    # ------------------------------------------------------------------
    # names

    def _referenced(self, node: Tree) -> frozenset[str]:
        """Every qubit name used anywhere under ``node``."""
        key = id(node)
        if key not in self._references:
            names: set[str] = set()
            if node.data == "qubit_ref":
                names.add(str(node.children[0]))
            elif node.data == "qubit_index":
                token = node.children[1].children[0]
                names.add(f"{node.children[0]}[{token}]")
            else:
                for child in node.children:
                    if isinstance(child, Tree):
                        names |= self._referenced(child)
            self._references[key] = frozenset(names)
        return self._references[key]

    def _used_later(self, name: str, frame: _Frame) -> bool:
        """Whether ``name`` is used again before the block that declares it ends."""
        depth = max(frame.declared[name], 0)
        return any(
            name in self._referenced(statement)
            for statements in frame.remaining[depth:]
            for statement in statements
        )

    @staticmethod
    def _index(node: Tree, frame: _Frame) -> int:
        token = node.children[0]
        if token.type == "NUMBER":
            return _integer(token, "an index")
        raise ValueError(f"{frame.where}: index {token} is not a for-loop variable")

    def _qubit_name(self, node: Tree, frame: _Frame) -> str:
        if node.data == "qubit_ref":
            return str(node.children[0])
        if node.data == "qubit_index":
            return f"{node.children[0]}[{self._index(node.children[1], frame)}]"
        raise NotImplementedError(f"unsupported qubit reference {node.data!r}")

    def _bit_name(self, node: Tree, frame: _Frame) -> str:
        if node.data == "bit_ref":
            return str(node.children[0])
        if node.data == "bit_index":
            return f"{node.children[0]}[{self._index(node.children[1], frame)}]"
        raise NotImplementedError(f"unsupported bit reference {node.data!r}")

    def _callback_call(self, node: Tree, frame: _Frame, *, selector: bool) -> tuple[str, list[str], list[SSAValue]]:
        """Resolve ``name(bits...)``; return the callee, the bit names and their values."""
        name = str(node.children[0])
        kind, table = ("selector", self.selector_arity) if selector else ("decoder", self.decoder_arity)
        if name not in table:
            raise ValueError(f"{frame.where}: @{name} is not a declared {kind}")
        arguments = node.children[1].children if len(node.children) > 1 else []
        bit_names = [self._bit_name(item, frame) for item in arguments if isinstance(item, Tree)]
        if len(bit_names) != table[name]:
            raise ValueError(f"{kind} @{name} expects {table[name]} bits, got {len(bit_names)}")
        return name, bit_names, [frame.read_bit(bit) for bit in bit_names]

    def _selector_call(
        self, node: Tree, frame: _Frame, *, statement: str, result: str
    ) -> tuple[str, list[str], list[SSAValue]]:
        selector, bit_names, bits = self._callback_call(node, frame, selector=True)
        if self.selector_result[selector] != result:
            raise ValueError(
                f"{frame.where}: a {statement} needs a selector declared -> {result}, "
                f"but @{selector} is declared -> {self.selector_result[selector]}"
            )
        return selector, bit_names, bits

    # ------------------------------------------------------------------
    # statements

    def _lower_block(self, statements: list[Tree], frame: _Frame, *, end: str = "before its block ends") -> None:
        frame.scopes.append([])
        frame.remaining.append([])
        for position, statement in enumerate(statements):
            frame.remaining[-1] = statements[position + 1 :]
            self._lower_statement(statement, frame)
        frame.remaining.pop()
        declared = frame.scopes.pop()
        live = [name for name in declared if name in frame.qubits]
        if live:
            message = f"{frame.where}: local qubit(s) {', '.join(live)} must be measured {end}"
            returned = [name for name in live if name in frame.from_select]
            if returned:
                message += (
                    f"; {', '.join(returned)} came back from a switch or while loop, so a qubit used only "
                    "inside its arms or body should be declared there"
                )
            raise ValueError(message)
        for name in declared:
            del frame.declared[name]

    def _lower_statement(self, statement: Tree, frame: _Frame) -> None:
        kind = statement.data
        if kind == "bit_stmt":
            return
        if kind == "scope":
            self._lower_block(_block_stmts(statement), frame)
        elif kind == "qubit_stmt":
            self._lower_qubit(statement, frame)
        elif kind == "apply_stmt":
            self._lower_apply(statement, frame)
        elif kind == "call_stmt":
            self._lower_call(statement, frame)
        elif kind == "measure_stmt":
            self._lower_measure(statement, frame)
        elif kind in {"decode_decl", "decode_assign"}:
            self._lower_decode(statement, frame)
        elif kind == "switch_stmt":
            self._lower_switch(statement, frame)
        elif kind == "while_stmt":
            self._lower_while(statement, frame)
        else:
            raise NotImplementedError(f"unsupported statement {kind!r}")

    def _lower_qubit(self, statement: Tree, frame: _Frame) -> None:
        *designator, identifier = statement.children
        names = [str(identifier)]
        if designator:
            size = _integer(designator[0].children[0], f"the size of {identifier}")
            names = [f"{identifier}[{index}]" for index in range(size)]
        depth = len(frame.scopes) - 1
        for name in names:
            if name in frame.declared:
                raise ValueError(f"{frame.where}: qubit {name} is already declared")
            frame.declared[name] = depth
            frame.scopes[-1].append(name)
            # A qubit the program never uses never enters the IR.
            if self._used_later(name, frame):
                frame.bind(name, frame.allocs.fresh_qubit())

    def _lower_apply(self, statement: Tree, frame: _Frame) -> None:
        name = str(statement.children[0])
        rest = list(statement.children[1:])
        params: list[float] = []
        if rest and _is_tree(rest[0], "gate_params"):
            params = [float(item.children[0]) for item in rest[0].children if _is_tree(item, "gate_param")]
            rest = rest[1:]
        if name in self.kernels:
            raise ValueError(f"{frame.where}: @{name} is a def, so it is called as {name}(...)")
        if name not in self.include_gates.gates:
            raise NotImplementedError(f"unknown apply target {name!r}")
        arg_names = [self._qubit_name(item, frame) for item in rest if isinstance(item, Tree)]
        operands = [frame.value(arg) for arg in arg_names]
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
        frame.block.add_op(gate)
        for arg_name, result in zip(arg_names, gate.results, strict=True):
            frame.bind(arg_name, result)

    def _lower_call(self, statement: Tree, frame: _Frame) -> None:
        name = str(statement.children[0])
        if name not in self.kernels:
            hint = ", a gate, is applied without parentheses" if name in self.include_gates.gates else " is not a def"
            raise ValueError(f"{frame.where}: {name}{hint}")
        arg_names = [self._qubit_name(item, frame) for item in statement.children[1:]]
        operands = [frame.value(arg) for arg in arg_names]
        signature = self.kernels[name]
        if len(operands) != len(signature.inputs):
            raise ValueError(f"def @{name} expects {len(signature.inputs)} qubits, got {len(operands)}")
        call = CallOp(name, operands, signature.results)
        frame.block.add_op(call)
        # Every argument comes back, in order: a call is opaque, and the
        # caller cannot tell -- and is not told -- which of its returned
        # qubits are physically fresh |0>s substituted by the callee.
        for arg_name, result in zip(arg_names, call.results, strict=True):
            frame.bind(arg_name, result)

    def _lower_measure(self, statement: Tree, frame: _Frame) -> None:
        qubit_name = self._qubit_name(statement.children[0], frame)
        bit_name = self._bit_name(statement.children[1], frame)
        measure = MeasureOp(operand=frame.value(qubit_name))
        frame.block.add_op(measure)
        frame.bits[bit_name] = measure.result
        if qubit_name in frame.borrowed or self._used_later(qubit_name, frame):
            # Measurement plus reset: the name now holds a fresh |0>.
            frame.bind(qubit_name, frame.allocs.fresh_qubit())
        else:
            del frame.qubits[qubit_name]
            frame.from_select.discard(qubit_name)

    def _lower_decode(self, statement: Tree, frame: _Frame) -> None:
        target, call = statement.children
        bit_name = str(target) if isinstance(target, Token) else self._bit_name(target, frame)
        callee, _, bits = self._callback_call(call, frame, selector=False)
        decode = DecodeOp(callee=callee, bit_operands=bits)
        frame.block.add_op(decode)
        frame.bits[bit_name] = decode.result

    def _rebind_from_select(self, frame: _Frame, live: list[str], select: SelectOp) -> None:
        frame.block.add_op(select)
        for name, result in zip(live, select.results, strict=True):
            frame.bind(name, result)
            frame.from_select.add(name)

    def _lower_switch(self, statement: Tree, frame: _Frame) -> None:
        selector, _, bits = self._selector_call(statement.children[0], frame, statement="switch", result="int")
        live = list(frame.qubits)
        cases: dict[str, SymbolRefAttr] = {}
        for arm in [child for child in statement.children[1:] if _is_tree(child, "case_arm")]:
            label = str(_integer(arm.children[0], "a case label"))
            if label in cases:
                raise ValueError(f"{frame.where}: duplicate case {label} in the switch on @{selector}")
            self.case_counter += 1
            name = f"__qstack_case_{label}_{self.case_counter}"
            where = f"case {label} of the switch on @{selector}"
            self._generated_kernel(name, where, _block_stmts(arm.children[1]), live)
            cases[label] = SymbolRefAttr(name)
        select = SelectOp(
            callee=selector,
            bit_operands=bits,
            cases=cases,
            case_arguments=[frame.qubits[name] for name in live],
            result_types=[QubitType() for _ in live],
        )
        self._rebind_from_select(frame, live, select)

    def _lower_while(self, statement: Tree, frame: _Frame) -> None:
        call, body = statement.children
        selector, bit_names, bits = self._selector_call(call, frame, statement="while", result="bool")
        live = list(frame.qubits)
        self.loop_counter += 1
        loop_name = f"__qstack_while_{self.loop_counter}"
        exit_name = f"__qstack_while_{self.loop_counter}_exit"
        cases = {WHILE_CONTINUE: SymbolRefAttr(loop_name), WHILE_EXIT: SymbolRefAttr(exit_name)}
        types = [QubitType() for _ in live]

        self._generated_kernel(exit_name, f"the exit of the while loop on @{selector}", [], live)

        # The loop kernel: the body, then the same select as at the loop.
        self.kernels[loop_name] = _KernelDecl(tuple(types), tuple(types))
        loop = self._frame(f"the body of the while loop on @{selector}", live)
        self._lower_block(_block_stmts(body), loop)
        unmeasured = [bit for bit in bit_names if bit not in loop.bits]
        if unmeasured:
            raise ValueError(
                f"{loop.where}: the body must measure {', '.join(unmeasured)}, which the loop condition reads"
            )
        tail_bits = [loop.read_bit(bit) for bit in bit_names]
        tail = SelectOp(
            callee=selector,
            bit_operands=tail_bits,
            cases=cases,
            case_arguments=self._finish(loop),
            result_types=types,
        )
        loop.block.add_op(tail)
        loop.block.add_op(ReturnOp(operands=list(tail.results)))
        self._add_kernel(loop_name, loop, list(types))

        select = SelectOp(
            callee=selector,
            bit_operands=bits,
            cases=cases,
            case_arguments=[frame.qubits[name] for name in live],
            result_types=types,
        )
        self._rebind_from_select(frame, live, select)


def lower(tree: Tree) -> ModuleOp:
    return _Lower().lower(tree)
