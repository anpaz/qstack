"""Lower a parsed qstack-OpenQASM Tree into a qstack MLIR ``ModuleOp``.

Phase 3b minimal scope, geared at the headline ``prepare_one.qasm``:

  - extern selector ``NAME(bit, ...)`` and extern decoder ``NAME(bit, ...) -> bit``
    become body-less ``func.func`` declarations carrying ``qstack.selector`` /
    ``qstack.decoder`` unit attributes.
  - ``def NAME(qubit q, ...) { body }`` becomes a ``func.func``. If the body
    has a ``qreg`` allocation, statements up to the (single, terminal)
    ``switch`` are wrapped in a ``qstack.kernel``; the switch lowers to
    ``qstack.select`` + ``qstack.invoke`` at function scope.
  - Each ``case N: { ... }`` body becomes a fresh auto-generated
    ``func.func`` continuation with signature
    ``(qubit×n) -> (qubit×n)`` over the qubits live at the switch.
  - Built-in cliffords (``h``, ``x``, ``z``, ``s``, ``cx``, ``cz``) are
    recognised by name; any other ``apply_stmt`` is treated as a call to a
    user-defined ``func.func``.
  - Top-level statements lower to ``func.func @main``.

Constraints that fall outside this scope (multi-switch defs, post-switch
statements, mid-switch in nested scopes, ``int`` parameters, declared
``return_type``, etc.) raise ``NotImplementedError`` rather than silently
miscompiling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from lark import Token, Tree
from xdsl.dialects.builtin import (
    DictionaryAttr,
    Float64Type,
    FloatAttr,
    FunctionType,
    ModuleOp,
    StringAttr,
    SymbolRefAttr,
    UnitAttr,
)
from xdsl.dialects.func import CallOp, FuncOp, ReturnOp as FuncReturn
from xdsl.ir import Block, Operation, Region, SSAValue

from qstack.dialect import BitType, QubitType
from qstack.dialect.core import InvokeOp, KernelOp, MeasureOp, ReturnOp, SelectOp
from qstack.surface.isa_includes import IncludeGateSet, resolve_includes


# ---------------------------------------------------------------------------
# Tree-shape helpers
# ---------------------------------------------------------------------------


def _is_tree(node: object, *names: str) -> bool:
    return isinstance(node, Tree) and node.data in names


def _ident(node: Tree | Token) -> str:
    if isinstance(node, Token):
        return str(node)
    # apply_stmt's first child is an IDENT Token; selector_call same.
    raise TypeError(f"expected IDENT token, got {node!r}")


def _qubit_arg_name(node: Tree) -> str:
    """Canonical name for a qubit reference (``q`` or ``ancilla[0]``)."""
    if node.data == "qubit_ref":
        return str(node.children[0])
    if node.data == "qubit_index":
        return f"{node.children[0]}[{node.children[1]}]"
    raise NotImplementedError(f"qubit arg shape: {node.data}")


def _bit_target_name(node: Tree) -> str:
    if node.data == "bit_ref":
        return str(node.children[0])
    if node.data == "bit_index":
        return f"{node.children[0]}[{node.children[1]}]"
    raise NotImplementedError(f"bit target shape: {node.data}")


def _block_stmts(block_tree: Tree) -> list[Tree]:
    return [c for c in block_tree.children if isinstance(c, Tree)]


# ---------------------------------------------------------------------------
# Lowering state
# ---------------------------------------------------------------------------


@dataclass
class _Env:
    """Per-scope SSA bindings for qasm qubit/bit names."""

    qubits: dict[str, SSAValue] = field(default_factory=dict)
    bits: dict[str, SSAValue] = field(default_factory=dict)
    # Order in which qubits were *introduced* in the current scope; used to
    # produce a deterministic threading order at kernel boundaries.
    qubit_order: list[str] = field(default_factory=list)

    def add_qubit(self, name: str, val: SSAValue) -> None:
        if name not in self.qubits:
            self.qubit_order.append(name)
        self.qubits[name] = val

    def drop_qubit(self, name: str) -> None:
        del self.qubits[name]
        self.qubit_order.remove(name)


class _Lower:
    def __init__(self) -> None:
        self.module = ModuleOp([])
        self.defs: dict[str, FunctionType] = {}  # user-def signatures
        self.case_counter = 0  # for auto-generated continuation names
        self.include_gates = IncludeGateSet(includes=(), gates={})

    # -- public ---------------------------------------------------------

    def lower(self, tree: Tree) -> ModuleOp:
        if tree.data != "start":
            raise ValueError(f"expected start tree, got {tree.data!r}")
        self.include_gates = resolve_includes(
            [ch for ch in tree.children if _is_tree(ch, "include")]
        )
        # Pass 1: hoist user-def signatures so call-sites can resolve.
        for ch in tree.children:
            if _is_tree(ch, "def_decl"):
                name, params = self._def_signature(ch)
                # Return signature inferred later, but for call resolution we
                # only need input arity/types. We provisionally register
                # `(qubit×n) -> (qubit×n)`; the actual def emission will
                # update it.
                input_tys = [QubitType()] * len(params)
                self.defs[name] = FunctionType.from_lists(input_tys, list(input_tys))
        # Pass 2: emit ops in source order, except top-level stmts go last.
        top_stmts: list[Tree] = []
        for ch in tree.children:
            if not isinstance(ch, Tree):
                continue
            if ch.data == "extern_decl":
                self.module.body.block.add_op(self._build_extern(ch, selector=False))
            elif ch.data == "selector_decl":
                self.module.body.block.add_op(self._build_extern(ch, selector=True))
            elif ch.data == "def_decl":
                self._build_def(ch)
            elif ch.data in {"qreg_stmt", "creg_stmt", "apply_stmt", "measure_stmt"}:
                top_stmts.append(ch)
            # header / include nodes are handled before lowering source ops.
        if top_stmts:
            self._build_main(top_stmts)
        return self.module

    # -- declarations ---------------------------------------------------

    def _build_extern(self, node: Tree, *, selector: bool) -> FuncOp:
        name = str(node.children[0])
        type_list = node.children[1]  # Tree('type_list', [...])
        return_type = node.children[2]  # Tree('qubit_type'/'bit_type'/'int_type', [])
        in_tys = [self._lower_type(t) for t in type_list.children]
        out_tys: list = [] if selector else [self._lower_type(return_type)]
        fn = FuncOp.external(name, in_tys, out_tys)
        fn.attributes["qstack.selector" if selector else "qstack.decoder"] = UnitAttr()
        return fn

    def _lower_type(self, node: Tree):
        if node.data == "qubit_type":
            return QubitType()
        if node.data == "bit_type":
            return BitType()
        raise NotImplementedError(f"type {node.data!r} not supported")

    # -- def -----------------------------------------------------------

    def _def_signature(self, node: Tree) -> tuple[str, list[tuple[str, str]]]:
        name = str(node.children[0])
        params: list[tuple[str, str]] = []
        for ch in node.children[1:]:
            if _is_tree(ch, "param_list"):
                for p in ch.children:
                    ty = p.children[0].data  # 'qubit_type' / 'bit_type'
                    pname = str(p.children[1])
                    params.append((ty, pname))
        return name, params

    def _build_def(self, node: Tree) -> None:
        name, params = self._def_signature(node)
        # All parameters must be qubits in this surface scope (prepare_one).
        for ty, _ in params:
            if ty != "qubit_type":
                raise NotImplementedError(f"def {name!r}: non-qubit parameter {ty!r}")
        body_tree = next(c for c in node.children if _is_tree(c, "block"))

        # Build the function with placeholder result types; rewrite after.
        in_tys = [QubitType()] * len(params)
        entry = Block(arg_types=list(in_tys))
        env = _Env()
        for (_, pname), ssa in zip(params, entry.args):
            env.add_qubit(pname, ssa)

        out_tys = self._emit_body(entry, env, body_tree, defining_func=name)
        fn = FuncOp(name, FunctionType.from_lists(in_tys, out_tys), Region([entry]))
        self.defs[name] = fn.function_type
        self.module.body.block.add_op(fn)

    def _build_main(self, stmts: list[Tree]) -> None:
        entry = Block(arg_types=[])
        env = _Env()
        # Top-level qreg/creg are processed as "intrinsic" allocations of
        # the synthesized main function; we model this by wrapping the body
        # in a synthetic block tree the body lowerer already understands.
        synthetic_block = Tree("block", stmts)
        out_tys = self._emit_body(entry, env, synthetic_block, defining_func="main")
        fn = FuncOp("main", FunctionType.from_lists([], out_tys), Region([entry]))
        self.module.body.block.add_op(fn)

    # -- body lowering -------------------------------------------------

    def _emit_body(
        self,
        outer: Block,
        env: _Env,
        body: Tree,
        *,
        defining_func: str,
    ) -> list:
        """Emit a func.func body. Returns the function's output types."""
        stmts = _block_stmts(body)
        # Partition into pre-switch and the switch (if any). Statements after
        # a switch are not supported in this minimal scope.
        switch_idx = next((i for i, s in enumerate(stmts) if s.data == "switch_stmt"), -1)
        if switch_idx == -1:
            pre, switch = stmts, None
            post: list[Tree] = []
        else:
            pre, switch = stmts[:switch_idx], stmts[switch_idx]
            post = stmts[switch_idx + 1 :]
        if post:
            raise NotImplementedError(f"@{defining_func}: statements after `switch` are not yet supported")

        # Discover qreg allocations among `pre` statements.
        allocs: list[tuple[str, int]] = []  # (qreg_name, count)
        cregs: list[tuple[str, int]] = []
        rest_pre: list[Tree] = []
        for s in pre:
            if s.data == "qreg_stmt":
                allocs.append((str(s.children[0]), int(s.children[1])))
            elif s.data == "creg_stmt":
                cregs.append((str(s.children[0]), int(s.children[1])))
            elif s.data == "bit_stmt":
                # Declarations only; binding happens at measure-time.
                pass
            else:
                rest_pre.append(s)

        needs_kernel = bool(allocs) or _has_measure(rest_pre)

        if not needs_kernel:
            # Pure threading body (e.g. an identity helper or a `def f { cx
            # a, b; }` style). Emit gate/call statements directly into the
            # function block; return all live qubits in introduction order.
            for s in rest_pre:
                self._lower_stmt(s, outer, env)
            # Top-level `main` with no kernel doesn't happen in scope; defs
            # without measure return all live qubits.
            qubit_returns = [env.qubits[n] for n in env.qubit_order]
            outer.add_op(FuncReturn.create(operands=qubit_returns))
            return [QubitType()] * len(qubit_returns)

        # --- kernel path -------------------------------------------------
        # Build kernel entry-block with one arg per allocated qubit, in the
        # order they appear in the qreg statement(s).
        alloc_names: list[str] = []
        for qreg_name, count in allocs:
            for i in range(count):
                alloc_names.append(f"{qreg_name}[{i}]" if count > 1 or "[" in qreg_name else qreg_name)
                # For the canonical OpenQASM form `qreg q[1]; q[0]`, indexing
                # is always present even when count==1; we always use [i].
        # Simpler & always-correct naming: always index.
        alloc_names = [f"{qreg}[{i}]" for qreg, count in allocs for i in range(count)]

        kbody = Block(arg_types=[QubitType()] * len(alloc_names))
        kenv = _Env(
            qubits={**env.qubits},
            bits={**env.bits},
            qubit_order=list(env.qubit_order),
        )
        for name, ssa in zip(alloc_names, kbody.args):
            kenv.add_qubit(name, ssa)

        for s in rest_pre:
            self._lower_stmt(s, kbody, kenv)

        # Determine bits to surface (those consumed by the switch) and
        # qubits to thread (all currently-live ones, in introduction order).
        if switch is not None:
            sel = switch.children[0]
            assert _is_tree(sel, "selector_call")
            bit_args_node = sel.children[1] if len(sel.children) > 1 else None
            bit_arg_nodes = (
                [c for c in bit_args_node.children if isinstance(c, Tree)] if bit_args_node is not None else []
            )
            surfaced_bit_names = [_bit_target_name(b) for b in bit_arg_nodes]
        else:
            surfaced_bit_names = [n for n in kenv.bits.keys()]

        surfaced_bits = [kenv.bits[n] for n in surfaced_bit_names]
        threaded_qubits = [kenv.qubits[n] for n in kenv.qubit_order]

        kbody.add_op(ReturnOp(operands=[*surfaced_bits, *threaded_qubits]))
        result_types = [BitType()] * len(surfaced_bits) + [QubitType()] * len(threaded_qubits)
        kernel = KernelOp(result_types=result_types, region=Region([kbody]))
        outer.add_op(kernel)

        # Re-bind names in the outer env to kernel results.
        kres = list(kernel.results)
        for name, ssa in zip(surfaced_bit_names, kres[: len(surfaced_bits)]):
            env.bits[name] = ssa
        for name, ssa in zip(kenv.qubit_order, kres[len(surfaced_bits) :]):
            env.qubits[name] = ssa
            if name not in env.qubit_order:
                env.qubit_order.append(name)

        # --- post-kernel: optional switch -------------------------------
        if switch is not None:
            self._lower_switch(switch, outer, env)

        # --- function return --------------------------------------------
        # For `main`, we return the surfaced bits in declaration order.
        # For other defs, we return live qubits (linear threading).
        if defining_func == "main":
            ret_vals = [env.bits[n] for n in env.bits]
            outer.add_op(FuncReturn.create(operands=ret_vals))
            return [BitType()] * len(ret_vals)
        else:
            ret_vals = [env.qubits[n] for n in env.qubit_order]
            outer.add_op(FuncReturn.create(operands=ret_vals))
            return [QubitType()] * len(ret_vals)

    def _lower_switch(self, switch: Tree, outer: Block, env: _Env) -> None:
        sel_call = switch.children[0]
        callee = str(sel_call.children[0])
        bit_args_node = sel_call.children[1] if len(sel_call.children) > 1 else None
        bit_arg_nodes = [c for c in bit_args_node.children if isinstance(c, Tree)] if bit_args_node is not None else []
        bit_names_param = [f"b{i}" for i in range(len(bit_arg_nodes))]
        bit_operand_vals = [env.bits[_bit_target_name(b)] for b in bit_arg_nodes]

        # Continuation footprint = currently-live qubits in introduction order.
        live = list(env.qubit_order)
        cont_in_tys = [QubitType()] * len(live)
        cont_ty = FunctionType.from_lists(cont_in_tys, cont_in_tys)

        cases = [c for c in switch.children[1:] if _is_tree(c, "case_arm")]
        cont_menu: dict[str, SymbolRefAttr] = {}
        for case in cases:
            label = str(case.children[0])  # NUMBER token, used as string key
            case_block = case.children[1]
            helper_name = self._emit_case_helper(label, case_block, live)
            cont_menu[label] = SymbolRefAttr(helper_name)

        sel_op = SelectOp(
            callee=SymbolRefAttr(callee),
            bit_names=bit_names_param,
            bit_operands=bit_operand_vals,
            continuations=cont_menu,
            result_type=cont_ty,
        )
        outer.add_op(sel_op)

        inv = InvokeOp(
            callee=sel_op.result,
            args=[env.qubits[n] for n in live],
            result_types=cont_in_tys,
        )
        outer.add_op(inv)
        for name, ssa in zip(live, inv.results):
            env.qubits[name] = ssa

    def _emit_case_helper(
        self,
        label: str,
        case_block: Tree,
        live_qubit_names: list[str],
    ) -> str:
        self.case_counter += 1
        helper_name = f"__case_{label}_{self.case_counter}"
        in_tys = [QubitType()] * len(live_qubit_names)
        entry = Block(arg_types=list(in_tys))
        env = _Env()
        for name, ssa in zip(live_qubit_names, entry.args):
            env.add_qubit(name, ssa)
        for s in _block_stmts(case_block):
            self._lower_stmt(s, entry, env)
        # Continuation must return the same shape it received.
        rets = [env.qubits[n] for n in live_qubit_names]
        entry.add_op(FuncReturn.create(operands=rets))
        fn = FuncOp(helper_name, FunctionType.from_lists(in_tys, in_tys), Region([entry]))
        self.module.body.block.add_op(fn)
        return helper_name

    # -- per-statement lowering ----------------------------------------

    def _lower_stmt(self, s: Tree, block: Block, env: _Env) -> None:
        if s.data == "apply_stmt":
            self._lower_apply(s, block, env)
        elif s.data == "measure_stmt":
            self._lower_measure(s, block, env)
        elif s.data == "bit_stmt":
            # No-op: bit declarations are bound by measure.
            pass
        else:
            raise NotImplementedError(f"unsupported statement: {s.data}")

    def _lower_apply(self, s: Tree, block: Block, env: _Env) -> None:
        name = str(s.children[0])
        rest = list(s.children[1:])
        params: list[float] = []
        if rest and _is_tree(rest[0], "gate_params"):
            params = [float(c.children[0]) for c in rest[0].children if _is_tree(c, "gate_param")]
            rest = rest[1:]
        arg_trees = [c for c in rest if isinstance(c, Tree)]
        arg_names = [_qubit_arg_name(a) for a in arg_trees]
        arg_ssa = [env.qubits[n] for n in arg_names]

        if name in self.defs:
            if params:
                raise ValueError(f"def @{name} does not accept gate parameters")
            sig = self.defs[name]
            n = len(sig.inputs.data)
            if len(arg_ssa) != n:
                raise ValueError(f"call @{name} expects {n} args, got {len(arg_ssa)}")
            call = CallOp(name, arg_ssa, list(sig.outputs.data))
            block.add_op(call)
            for arg_name, out in zip(arg_names, call.results):
                env.qubits[arg_name] = out
        elif name in self.include_gates.gates:
            op = self._build_gate_op(name, params, arg_ssa)
            block.add_op(op)
            for arg_name, result in zip(arg_names, op.results):
                env.qubits[arg_name] = result
        else:
            if not self.include_gates.gates:
                raise NotImplementedError(
                    f"unknown apply target {name!r}; no included ISA gates"
                )
            raise NotImplementedError(
                f"unknown apply target {name!r}; gate is not declared by "
                "any include"
            )

    def _build_gate_op(
        self,
        name: str,
        params: list[float],
        qubits: list[SSAValue],
    ) -> Operation:
        decl = self.include_gates.gates[name]
        if len(params) != len(decl.params):
            raise ValueError(
                f"gate {name!r} expects {len(decl.params)} parameters, got {len(params)}"
            )
        if len(qubits) != decl.arity:
            raise ValueError(f"gate {name!r} expects {decl.arity} qubits, got {len(qubits)}")
        properties = {
            param_name: FloatAttr(float(value), Float64Type())
            for param_name, value in zip(decl.params, params)
        }
        return decl.op_type.create(
            operands=qubits,
            result_types=[QubitType()] * decl.arity,
            properties=properties,
        )

    def _lower_measure(self, s: Tree, block: Block, env: _Env) -> None:
        q_arg = s.children[0]
        b_target = s.children[1]
        q_name = _qubit_arg_name(q_arg)
        b_name = _bit_target_name(b_target)
        q_ssa = env.qubits[q_name]
        meas = MeasureOp(operand=q_ssa)
        block.add_op(meas)
        env.bits[b_name] = meas.result
        env.drop_qubit(q_name)


def _has_measure(stmts: Iterable[Tree]) -> bool:
    return any(s.data == "measure_stmt" for s in stmts)


def lower(tree: Tree) -> ModuleOp:
    return _Lower().lower(tree)
