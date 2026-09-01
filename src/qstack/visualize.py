"""Mermaid dataflow diagrams for qstack kernels.

The diagram follows the executable IR directly: operations are nodes and SSA
values are wires.  This makes qubit threading and qubit-to-bit measurement
boundaries visible without needing a separate circuit representation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from xdsl.dialects.builtin import ModuleOp
from xdsl.ir import SSAValue

from qstack.dialect.core import (
    BitType,
    CallOp,
    DecodeOp,
    KernelOp,
    QubitType,
    ReturnOp,
    SelectOp,
)


_ValueKind = Literal["qubit", "bit", "host", "other"]


@dataclass(frozen=True)
class _Edge:
    source: str
    target: str
    label: str
    kind: _ValueKind


@dataclass(frozen=True)
class _CallDefinition:
    """A called-kernel definition visually owned by one call-site node."""

    call_node: str
    diagram: "DataflowDiagram"


@dataclass(frozen=True)
class _Wire:
    source: str
    label: str
    kind: _ValueKind


@dataclass
class _InlineRegion:
    scope_id: str
    label: str
    node_ids: list[str]
    children: list["_InlineRegion"]


@dataclass(frozen=True)
class DataflowDiagram:
    """A dataflow view of one qstack kernel.

    Use :meth:`to_mermaid` for a portable textual diagram or :meth:`display`
    from an IPython notebook to render Mermaid-aware Markdown output.
    """

    kernel: str
    nodes: tuple[tuple[str, str, str], ...]
    edges: tuple[_Edge, ...]
    call_definitions: tuple[_CallDefinition, ...] = ()
    scope_id: str = ""
    inline_region: _InlineRegion | None = None

    def to_mermaid(self) -> str:
        """Serialize this diagram as a Mermaid ``flowchart``."""
        lines = ["flowchart TB"]
        if self.inline_region is not None:
            self._append_inline_mermaid(lines)
            return "\n".join(lines)
        self._append_mermaid(lines, "  ")
        return "\n".join(lines)

    def _append_inline_mermaid(self, lines: list[str]) -> None:
        assert self.inline_region is not None
        node_map = {node_id: (label, shape) for node_id, label, shape in self.nodes}

        def append_region(region: _InlineRegion, indent: str) -> None:
            lines.append(f'{indent}subgraph {region.scope_id}["{_escape(region.label)}"]')
            content_indent = f"{indent}  "
            lines.append(f"{content_indent}direction TB")
            for node_id in region.node_ids:
                label, shape = node_map[node_id]
                self._append_node(lines, content_indent, node_id, label, shape)
            for child in region.children:
                append_region(child, content_indent)
            lines.append(f"{indent}end")

        append_region(self.inline_region, "  ")
        for edge in self.edges:
            label = _escape(edge.label)
            if edge.kind == "bit":
                lines.append(f'  {edge.source} == "{label}" ==> {edge.target}')
            elif edge.kind == "host":
                lines.append(f'  {edge.source} -. "{label}" .-> {edge.target}')
            else:
                lines.append(f'  {edge.source} -- "{label}" --> {edge.target}')

    def _append_mermaid(self, lines: list[str], indent: str) -> None:
        scope_id = self.scope_id or f"kernel_{_identifier(self.kernel)}"
        lines.append(f'{indent}subgraph {scope_id}["@{_escape(self.kernel)}"]')
        content_indent = f"{indent}  "
        definitions = {definition.call_node: definition for definition in self.call_definitions}
        for node_id, label, shape in self.nodes:
            definition = definitions.get(node_id)
            if definition is not None:
                call_scope = f"call_{scope_id}_{node_id}"
                lines.append(f'{content_indent}subgraph {call_scope}["call @{_escape(definition.diagram.kernel)}"]')
                self._append_node(lines, f"{content_indent}  ", node_id, label, shape)
                definition.diagram._append_mermaid(lines, f"{content_indent}  ")
                lines.append(f"{content_indent}end")
                continue
            self._append_node(lines, content_indent, node_id, label, shape)
        for edge in self.edges:
            label = _escape(edge.label)
            if edge.kind == "bit":
                lines.append(f'{content_indent}{edge.source} == "{label}" ==> {edge.target}')
            elif edge.kind == "host":
                lines.append(f'{content_indent}{edge.source} -. "{label}" .-> {edge.target}')
            else:
                lines.append(f'{content_indent}{edge.source} -- "{label}" --> {edge.target}')
        lines.append(f"{indent}end")

    @staticmethod
    def _append_node(
        lines: list[str], indent: str, node_id: str, label: str, shape: str
    ) -> None:
        escaped = _escape(label)
        if shape == "source":
            lines.append(f'{indent}{node_id}(["{escaped}"])')
        elif shape == "host-source":
            lines.append(f'{indent}{node_id}(("{escaped}"))')
        elif shape == "host":
            lines.append(f'{indent}{node_id}[["{escaped}"]]')
        elif shape == "measure":
            lines.append(f'{indent}{node_id}{{{{"{escaped}"}}}}')
        else:
            lines.append(f'{indent}{node_id}["{escaped}"]')

    def display(self) -> None:
        """Display this diagram in an IPython environment.

        Jupyter frontends that support Mermaid fenced Markdown render the
        diagram inline. Other frontends still show the Mermaid source, which
        can be copied into a Mermaid-compatible renderer.
        """
        try:
            from IPython.display import Markdown, display
        except ImportError as error:  # pragma: no cover - depends on optional IPython
            raise RuntimeError("DataflowDiagram.display() requires IPython") from error
        display(Markdown(f"```mermaid\n{self.to_mermaid()}\n```"))


def dataflow(
    module: ModuleOp, *, kernel: str = "main", inline_calls: bool = True
) -> DataflowDiagram:
    """Return the SSA dataflow diagram for ``@kernel`` in ``module``.

    Args:
        module: A qstack module.
        kernel: Name of the kernel to visualize, without the ``@`` prefix.
        inline_calls: Inline direct kernel calls into one dataflow graph.

    Raises:
        ValueError: If the requested kernel is absent.
    """
    target = next(
        (
            op
            for op in module.body.ops
            if isinstance(op, KernelOp) and op.sym_name.data == kernel
        ),
        None,
    )
    if target is None:
        raise ValueError(f"No qstack kernel named @{kernel}")
    kernels = {
        op.sym_name.data: op
        for op in module.body.ops
        if isinstance(op, KernelOp)
    }
    host_reachable = _host_reachable_kernels(kernels)
    if inline_calls:
        return _flatten_dataflow(target, kernels, host_reachable)
    included = {target.sym_name.data}

    def build(kernel_op: KernelOp, scope_id: str) -> DataflowDiagram:
        definitions = []
        for index, op in enumerate(kernel_op.body.blocks[0].ops):
            if not isinstance(op, CallOp):
                continue
            callee = op.callee.root_reference.data
            if callee not in kernels or callee in included:
                continue
            included.add(callee)
            definitions.append(
                _CallDefinition(
                    f"{'' if kernel_op is target else f'{scope_id}_'}op{index}",
                    build(kernels[callee], f"kernel_{_identifier(callee)}"),
                )
            )
        node_prefix = "" if kernel_op is target else f"{scope_id}_"
        diagram = _kernel_dataflow(kernel_op, host_reachable, node_prefix)
        return replace(
            diagram, call_definitions=tuple(definitions), scope_id=scope_id
        )

    return build(target, f"kernel_{_identifier(target.sym_name.data)}")


def _flatten_dataflow(
    root: KernelOp, kernels: dict[str, KernelOp], host_reachable: set[str]
) -> DataflowDiagram:
    """Inline direct calls, retaining only recursive call boundaries."""
    nodes: list[tuple[str, str, str]] = []
    edges: list[_Edge] = []
    host_nodes: list[str] = []
    invocation_count = 0
    root_region = _InlineRegion("kernel_root", f"@{root.sym_name.data}", [], [])

    def add_node(region: _InlineRegion, node_id: str, label: str, shape: str) -> None:
        nodes.append((node_id, label, shape))
        region.node_ids.append(node_id)

    def emit_kernel(
        kernel: KernelOp,
        arguments: list[_Wire],
        context: str,
        active: frozenset[str],
        region: _InlineRegion,
        *,
        is_root: bool = False,
    ) -> list[_Wire]:
        nonlocal invocation_count
        block = kernel.body.blocks[0]
        wires: dict[SSAValue, _Wire] = {}
        names: dict[SSAValue, str] = {}
        next_ssa_index = 0

        def value_name(value: SSAValue) -> str:
            nonlocal next_ssa_index
            if value in names:
                return names[value]
            hint = getattr(value, "name_hint", None)
            name = hint if hint and hint.startswith("%") else f"%{hint}" if hint else f"%{next_ssa_index}"
            next_ssa_index += not bool(hint)
            # Regions identify inlined invocations; preserve the kernel's SSA
            # spelling on wires rather than leaking that implementation scope.
            names[value] = name
            return names[value]

        for index, argument in enumerate(block.args[: len(kernel.input_types)]):
            if is_root:
                node_id = f"arg{index}"
                add_node(region, node_id, f"{value_name(argument)} (input)", "source")
                wires[argument] = _Wire(node_id, value_name(argument), _value_kind(argument))
            else:
                wires[argument] = arguments[index]
                value_name(argument)
        for index, argument in enumerate(block.args[len(kernel.input_types) :]):
            entry_index = len(kernel.input_types) + index
            node_id = f"arg{entry_index}" if is_root else f"{context}_arg{entry_index}"
            add_node(region, node_id, f"{value_name(argument)} (fresh)", "source")
            wires[argument] = _Wire(node_id, value_name(argument), "qubit")

        for index, op in enumerate(block.ops):
            if isinstance(op, ReturnOp):
                returned = [wires[operand] for operand in op.operands]
                if is_root:
                    add_node(region, "return", "return", "sink")
                    for wire in returned:
                        edges.append(_Edge(wire.source, "return", wire.label, wire.kind))
                return returned

            if isinstance(op, CallOp):
                callee_name = op.callee.root_reference.data
                if callee_name in kernels and callee_name not in active:
                    invocation_count += 1
                    callee_context = f"{context}_{_identifier(callee_name)}_{invocation_count}"
                    callee_region = _InlineRegion(
                        f"inline_{callee_context}", f"@{callee_name}", [], []
                    )
                    region.children.append(callee_region)
                    returned = emit_kernel(
                        kernels[callee_name], [wires[value] for value in op.arguments],
                        callee_context, active | {callee_name}, callee_region,
                    )
                    for result, wire in zip(op.results, returned, strict=True):
                        wires[result] = _Wire(wire.source, value_name(result), wire.kind)
                    continue

            node_id = f"op{index}" if is_root else f"{context}_op{index}"
            shape = _operation_shape(op, host_reachable)
            add_node(region, node_id, _operation_label(op), shape)
            if shape == "host":
                host_nodes.append(node_id)
            for operand in op.operands:
                wire = wires[operand]
                edges.append(_Edge(wire.source, node_id, wire.label, wire.kind))
            for result in op.results:
                wires[result] = _Wire(node_id, value_name(result), _value_kind(result))

        raise AssertionError(f"kernel @{kernel.sym_name.data} has no return")

    emit_kernel(
        root, [], "root", frozenset({root.sym_name.data}), root_region, is_root=True
    )
    previous_host_node = "hostIn"
    add_node(root_region, previous_host_node, "host", "host-source")
    for host_node in host_nodes:
        edges.append(_Edge(previous_host_node, host_node, "host", "host"))
        previous_host_node = host_node
    edges.append(_Edge(previous_host_node, "return", "host", "host"))
    return DataflowDiagram(
        root.sym_name.data, tuple(nodes), tuple(edges), inline_region=root_region
    )


def _kernel_dataflow(
    kernel: KernelOp, host_reachable: set[str], node_prefix: str = ""
) -> DataflowDiagram:
    block = kernel.body.blocks[0]
    nodes: list[tuple[str, str, str]] = []
    edges: list[_Edge] = []
    producers: dict[SSAValue, str] = {}
    names: dict[SSAValue, str] = {}
    ssa_index = 0

    def value_name(value: SSAValue) -> str:
        nonlocal ssa_index
        if value in names:
            return names[value]
        hint = getattr(value, "name_hint", None)
        if hint:
            name = hint if hint.startswith("%") else f"%{hint}"
        else:
            name = f"%{ssa_index}"
            ssa_index += 1
        names[value] = name
        return name

    for index, argument in enumerate(block.args):
        source_id = f"{node_prefix}arg{index}"
        origin = "input" if index < len(kernel.input_types) else "fresh"
        nodes.append((source_id, f"{value_name(argument)} ({origin})", "source"))
        producers[argument] = source_id

    host_nodes: list[str] = []
    for index, op in enumerate(block.ops):
        if isinstance(op, ReturnOp):
            target_id = f"{node_prefix}return"
            nodes.append((target_id, "return", "sink"))
        else:
            target_id = f"{node_prefix}op{index}"
            shape = _operation_shape(op, host_reachable)
            nodes.append((target_id, _operation_label(op), shape))
            if shape == "host":
                host_nodes.append(target_id)
        for operand in op.operands:
            edges.append(_Edge(producers[operand], target_id, value_name(operand), _value_kind(operand)))
        if not isinstance(op, ReturnOp):
            for result in op.results:
                producers[result] = target_id
                value_name(result)

    previous_host_node = f"{node_prefix}hostIn"
    nodes.append((previous_host_node, "host", "host-source"))
    for host_node in host_nodes:
        edges.append(_Edge(previous_host_node, host_node, "host", "host"))
        previous_host_node = host_node
    edges.append(_Edge(previous_host_node, f"{node_prefix}return", "host", "host"))

    return DataflowDiagram(kernel.sym_name.data, tuple(nodes), tuple(edges))


def _operation_label(op) -> str:
    label = op.name.removeprefix("qstack.")
    if not op.name.startswith("qstack."):
        label = op.name.rpartition(".")[2]
    if hasattr(op, "callee"):
        reference = op.callee.root_reference.data
        label = f"{label} @{reference}"
    if op.name == "qstack.select":
        cases = ", ".join(
            f"{case}: @{target.root_reference.data}"
            for case, target in op.cases.data.items()
        )
        label = f"{label}<br/>{{{cases}}}"
    properties = [
        f"{name} = {_property_value(attribute)}"
        for name, attribute in op.properties.items()
        if name not in {"callee", "cases", "operand_segment_sizes"}
    ]
    if properties:
        label = f"{label}<br/>{'<br/>'.join(properties)}"
    return label


def _property_value(attribute) -> str:
    """Format an operation property compactly for a Mermaid node label."""
    value = getattr(attribute, "value", attribute)
    value = getattr(value, "data", value)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _operation_shape(op, host_reachable: set[str]) -> str:
    if isinstance(op, (DecodeOp, SelectOp)):
        return "host"
    if isinstance(op, CallOp) and op.callee.root_reference.data in host_reachable:
        return "host"
    if op.name == "qstack.measure":
        return "measure"
    return "operation"


def _host_reachable_kernels(kernels: dict[str, KernelOp]) -> set[str]:
    """Return kernels whose execution can invoke a host callback."""

    def reaches_host(start: str) -> bool:
        pending = [start]
        visited: set[str] = set()
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            operations = tuple(kernels[name].body.blocks[0].ops)
            if any(isinstance(op, (DecodeOp, SelectOp)) for op in operations):
                return True
            pending.extend(
                op.callee.root_reference.data
                for op in operations
                if isinstance(op, CallOp) and op.callee.root_reference.data in kernels
            )
        return False

    return {name for name in kernels if reaches_host(name)}


def _value_kind(value: SSAValue) -> _ValueKind:
    if isinstance(value.type, QubitType):
        return "qubit"
    if isinstance(value.type, BitType):
        return "bit"
    return "other"


def _escape(label: str) -> str:
    return label.replace('"', "#quot;")


def _identifier(name: str) -> str:
    """Return a Mermaid-safe identifier while retaining readable symbols."""
    return "".join(character if character.isalnum() else "_" for character in name)
