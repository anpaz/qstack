"""Export an interactive, offline report for a saved compilation witness."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections import defaultdict
from html import escape
from importlib.resources import files
from pathlib import Path
from string import Template
from typing import Sequence

from xdsl.dialects.builtin import ModuleOp

from qstack.compilation import (
    ArtifactError, CompilationArtifact, CompilationResult, load_artifact, module_text, parse_module,
)
from qstack.dialect.core import BitType
from qstack.verification import (
    Claim, KernelBoundary, Pattern, Rule, RuleResult, ValueRef, VerificationReport, Witness,
)
from qstack.verification.patterns import QUBIT
from qstack.verification.witness_check import _callback_sources, _host_sequence, _kernels


BIT = str(BitType())
_DEFAULT_OUTPUT = "docket.html"
_RULE_MARKS = {"VERIFIED": "✓", "REFUTED": "×", "UNSUPPORTED": "?", "NOT_CHECKED": "○"}


class _Graph:
    def __init__(self, *, direction: str = "LR") -> None:
        self.lines = [
            "digraph {",
            f'graph [rankdir={direction}, bgcolor="transparent", pad=0.15, nodesep=0.26]',
            'node [shape=box, style="rounded,filled", fontname="sans-serif", fontsize=12]',
            'edge [fontname="sans-serif", fontsize=10, arrowsize=0.65]',
        ]

    def node(self, identifier: str, label: str, **attributes: str) -> None:
        self._add(identifier, label=label, **attributes)

    def edge(self, source: str, target: str, label: str, kind: str, **attributes: str) -> None:
        self._add(f"{source} -> {target}", label=label, **{"class": kind}, **attributes)

    def _add(self, expression: str, **attributes: str) -> None:
        props = ", ".join(f"{name}={json.dumps(value, ensure_ascii=False)}" for name, value in attributes.items())
        self.lines.append(f"{expression} [{props}]")

    def svg(self, dot: str, identifier: str) -> str:
        result = subprocess.run(
            [dot, "-Tsvg", f"-Gid={identifier}"],
            input="\n".join([*self.lines, "}"]),
            capture_output=True,
            encoding="utf-8",
        )
        if result.returncode or "<svg " not in result.stdout:
            raise ValueError(f"Graphviz could not draw {identifier}: {result.stderr.strip()}")
        return result.stdout[result.stdout.index("<svg "):]


def _wire_label(typ: str, width: int = 1) -> tuple[str, str]:
    if typ == QUBIT:
        return ("q" if width == 1 else f"q ×{width}"), "qubit"
    if typ == BIT:
        return "bit", "bit"
    return typ, "other"


def _pattern_graph(pattern: Pattern) -> _Graph:
    graph = _Graph()
    values: dict[ValueRef, tuple[str, str]] = {}
    for i, typ in enumerate(pattern.inputs):
        graph.node(f"arg{i}", f"in {i}", shape="oval")
        values[ValueRef("arg", i)] = f"arg{i}", typ
    last_host: dict[str, str] = {}
    for i, op in enumerate(pattern.operations):
        properties = [
            f"{name} = {value}"
            for name, value in op.properties
            if name != "operand_segment_sizes"
        ]
        graph.node(f"op{i}", "\n".join([op.name.removeprefix("qstack."), *properties]))
        for slot, typ in enumerate(op.result_types):
            values[ValueRef("result", i, slot)] = f"op{i}", typ
        for host in dict.fromkeys(op.hosts):
            label = _host_label(host)
            if host not in last_host:
                last_host[host] = f"host{len(last_host)}"
                graph.node(last_host[host], label, shape="oval")
            graph.edge(last_host[host], f"op{i}", label, "host")
            last_host[host] = f"op{i}"

    def connect(ref: ValueRef, target: str, port: int) -> None:
        if ref not in values:
            node = f"missing{len(values)}"
            graph.node(node, f"Invalid value {ref.kind} {ref.index}.{ref.slot}")
            values[ref] = node, ""
        producer, typ = values[ref]
        label, kind = _wire_label(typ)
        graph.edge(producer, target, label, kind, tooltip=f"{ref.kind} {ref.index}.{ref.slot} → port {port}")

    for i, op in enumerate(pattern.operations):
        for port, operand in enumerate(op.operands):
            connect(operand, f"op{i}", port)
    for i, ref in enumerate(pattern.outputs):
        graph.node(f"out{i}", f"out {i}", shape="oval")
        connect(ref, f"out{i}", i)
    if not values and not pattern.operations:
        graph.node("empty", "Empty pattern", shape="plaintext")
    return graph


def _host_label(host: str) -> str:
    return f"host {host}" if host else "host"


def _host_tracks(
    module: ModuleOp | None, claims_by_kernel: dict[str, list[Claim]],
    rules: dict[str, Rule], projection: str,
) -> dict[str, dict[str, tuple[str, ...]]]:
    if module is None:
        return {}
    sources = _callback_sources(module)
    tracks = {}
    for name, kernel in _kernels(module).items():
        claims = claims_by_kernel.get(name, [])
        if any(claim.rule not in rules for claim in claims):
            continue
        sites = [
            (index, claim)
            for claim in claims
            for index in getattr(claim, f"{projection}_ops")
        ]
        coverage = dict(sites)
        if len(coverage) == len(sites) and coverage.keys() == set(range(len(tuple(kernel.body.block.ops)))):
            tracks[name] = _host_sequence(
                kernel, coverage, rules, sources, source_side=projection == "source",
            )
    return tracks


def _operations(pattern: Pattern) -> str:
    names = [op.name.rsplit(".", 1)[-1] for op in pattern.operations[:4]]
    if len(pattern.operations) > len(names):
        names.append(f"+{len(pattern.operations) - len(names)} more")
    return " · ".join(names) or "∅"


def _rule_name(rule: Rule) -> str:
    source, target = _operations(rule.source), _operations(rule.target)
    return source if rule.kind == "identity" and rule.source == rule.target else f"{source} → {target}"


def _claim_graph(
    boundary: KernelBoundary, claims: list[Claim], witness: Witness, rules: dict[str, Rule],
    rule_links: dict[str, str], source_hosts: dict[str, tuple[str, ...]],
    target_hosts: dict[str, tuple[str, ...]], *, rule_statuses: dict[str, str | None],
) -> _Graph:
    graph = _Graph(direction="TB")
    producers: dict[str, list[tuple[str, str]]] = defaultdict(list)
    consumers: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    widths = {edge.id: len(edge.target) for edge in witness.edges if edge.kernel == boundary.name}
    nodes = {}
    for i, edge_id in enumerate(boundary.inputs):
        graph.node(f"arg{i}", f"in {i}", shape="oval")
        producers[edge_id].append((f"arg{i}", f"kernel input {i}"))
    for i, claim in enumerate(claims):
        rule = rules.get(claim.rule)
        node = f"claim{i}"
        nodes[claim.id] = node
        attrs = {"href": f"#{rule_links[claim.rule]}"} if claim.rule in rule_links else {}
        label = _rule_name(rule) if rule else claim.rule
        tooltip = f"{claim.id} · rule {claim.rule}"
        verdict = rule_statuses.get(claim.rule)
        if verdict is not None and verdict in _RULE_MARKS:
            label = f"{_RULE_MARKS[verdict]} {label}"
            tooltip += f" · {verdict.replace('_', ' ').lower()}"
            attrs["class"] = verdict.lower()
        graph.node(node, label, tooltip=tooltip, **attrs)
        for port, edge_id in enumerate(claim.outputs):
            producers[edge_id].append((node, f"output {port}"))
        for port, edge_id in enumerate(claim.inputs):
            typ = rule.source.inputs[port] if rule and port < len(rule.source.inputs) else ""
            consumers[edge_id].append((node, f"input {port}", typ))

    for i, edge_id in enumerate(dict.fromkeys((*widths, *producers, *consumers))):
        incoming, outgoing = producers[edge_id], consumers[edge_id]
        if not incoming:
            incoming = [(f"dangling_in{i}", "missing producer")]
            graph.node(incoming[0][0], f"{edge_id}\nmissing producer", shape="oval")
        if not outgoing:
            outgoing = [(f"dangling_out{i}", "missing consumer", "")]
            graph.node(outgoing[0][0], f"{edge_id}\nmissing consumer", shape="oval")
        for start, out_port in incoming:
            for end, in_port, typ in outgoing:
                label, kind = _wire_label(typ, widths.get(edge_id, 1))
                if edge_id not in widths:
                    label = "Undeclared edge"
                graph.edge(start, end, label, kind, tooltip=f"{edge_id} · {out_port} → {in_port}")

    for i, host in enumerate(dict.fromkeys((*source_hosts, *target_hosts))):
        label = _host_label(host)
        start = f"host{i}"
        graph.node(start, label, shape="oval")
        old = source_hosts.get(host, ())
        new = target_hosts.get(host, ())
        sequences = ((label, old),) if old == new else ((f"{label} · source", old), (f"{label} · target", new))
        for wire, sequence in sequences:
            chain = (start, *(nodes[claim] for claim in sequence))
            for before, after in zip(chain, chain[1:]):
                if before != after:
                    graph.edge(before, after, wire, "host")
    if not (boundary.inputs or claims or widths or source_hosts or target_hosts):
        graph.node("empty", "No claims", shape="plaintext")
    return graph


def _status(status: str | None) -> str:
    if status is None:
        return ""
    return f'<span class="status {escape(status.lower())}">{escape(status.replace("_", " "))}</span>'


def _rule_legend(verdicts: set[str | None]) -> str:
    entries = [
        f'<span class="{verdict.lower()}">{symbol} {verdict.replace("_", " ").capitalize()}</span>'
        for verdict, symbol in _RULE_MARKS.items()
        if verdict in verdicts
    ]
    return f'<p class="legend rule-legend"><strong>Rule verdicts</strong>{"".join(entries)}</p>' if entries else ""


def _navigation(label: str, entries: list[tuple[str, str, str]]) -> str:
    if not entries:
        return f'<h2>{label}</h2><p class="muted">None recorded</p>'
    return f'<h2>{label}</h2>' + "".join(
        f'<a href="#{link}"><span>{escape(name)}</span>{annotation}</a>'
        for link, name, annotation in entries
    )


def _backend_label(name: str, version: str | None) -> str:
    return f"{name} {version}" if version else name


def _available_backends(report: VerificationReport | None) -> str:
    if report is None:
        return ""
    available = ", ".join(report.available_backends or ())
    return f'<p><strong>Available rule backends</strong> {escape(available or "Not recorded")}</p>'


def _rule_panel(
    rule: Rule, report: RuleResult | None, sites: list[Claim], kernel_links: dict[str, str],
    dot: str, link: str, missing_status: str | None,
) -> str:
    verdict = _status(report.status if report else missing_status)
    backend = ""
    if report and report.backend == "none":
        backend = f"<p>{escape(report.detail)}</p>"
    elif report:
        name = escape(_backend_label(report.backend, report.backend_version))
        backend = f'<p><strong>Verifier</strong> {name} · {escape(report.detail)}</p>'
    if report and report.attempts and len(report.attempts) > 1:
        attempts = "".join(
            f'<li>{escape(_backend_label(attempt.backend, attempt.backend_version))} '
            f'{_status(attempt.status)} · {escape(attempt.detail)}</li>'
            for attempt in report.attempts
        )
        backend += f'<details><summary>Backends tried</summary><ol class="sites">{attempts}</ol></details>'
    diagrams = "".join(
        f'<section><h3>{side} pattern</h3><div class="graph-frame" role="region" '
        f'aria-label="{side} pattern" tabindex="0">{_pattern_graph(pattern).svg(dot, f"{link}-{side}")}</div></section>'
        for side, pattern in (("Source", rule.source), ("Target", rule.target))
    )
    site_rows = []
    for claim in sites:
        kernel = escape(f"@{claim.kernel}")
        if claim.kernel in kernel_links:
            kernel = f'<a href="#{kernel_links[claim.kernel]}">{kernel}</a>'
        source_ops = ", ".join(map(str, claim.source_ops)) or "∅"
        target_ops = ", ".join(map(str, claim.target_ops)) or "∅"
        site_rows.append(
            f'<li>{kernel} <code>{escape(claim.id)}</code> '
            f'<span class="muted">operations {source_ops} → {target_ops}</span></li>'
        )
    applications = f'<ul class="sites">{"".join(site_rows)}</ul>' if site_rows else '<p class="muted">None recorded</p>'
    return f"""
<section class="panel" id="{link}" data-panel tabindex="-1">
  <div class="panel-heading"><h2>{escape(_rule_name(rule))}</h2>{verdict}</div>
  <p class="muted">{escape(rule.kind)} rule · <code>{escape(rule.id)}</code></p>
  {backend}
  <div class="patterns">{diagrams}</div>
  <h3>Applications</h3>
  {applications}
</section>"""


def _match_report(
    report: VerificationReport, artifact: CompilationArtifact, artifact_path: Path,
) -> bool:
    """Check the report's association and indicate when it relies on a recorded path."""
    fingerprint = report.artifact_sha256
    matched_by_path = fingerprint is None
    if matched_by_path:
        try:
            if report.artifact_path is None:
                raise ArtifactError("no artifact path recorded")
            original_path = Path(report.artifact_path)
            original = artifact if original_path.resolve() == artifact_path.resolve() else load_artifact(original_path)
            fingerprint = original.fingerprint()
        except ArtifactError as exc:
            raise ValueError(
                "Verification report has no artifact fingerprint and its original artifact "
                "is unavailable. Run verify() on the saved compilation step and save the new report."
            ) from exc
    if fingerprint != artifact.fingerprint():
        raise ValueError("verification report belongs to a different compilation artifact")
    return matched_by_path


def generate_docket(
    compilation: CompilationResult | str | Path, output_path: str | Path = _DEFAULT_OUTPUT, *,
    report: VerificationReport | str | Path | None = None,
) -> Path:
    """Export a compilation witness and optional verification results to Docket HTML."""
    dot = shutil.which("dot")
    if dot is None:
        raise ValueError("Graphviz's dot executable is required to generate a docket")
    if isinstance(compilation, CompilationResult):
        if compilation.artifact_path is None:
            raise ValueError("the compilation result has no saved step artifact")
        artifact_path = compilation.artifact_path
    else:
        artifact_path = Path(compilation)
    output_path = Path(output_path)
    input_paths = [artifact_path]
    if isinstance(report, (str, Path)):
        input_paths.append(Path(report))
        report = VerificationReport.load(report)
    for path in input_paths:
        if path.resolve() == output_path.resolve() or (output_path.exists() and os.path.samefile(path, output_path)):
            raise ValueError("the HTML destination must differ from its inputs")

    artifact = load_artifact(artifact_path)
    if isinstance(compilation, CompilationResult) and (
        compilation.witness != artifact.witness or module_text(compilation.module) != artifact.target
    ):
        raise ValueError("compilation result differs from its saved step artifact")
    matched_by_path = report is not None and _match_report(report, artifact, artifact_path)
    missing_status = "NOT_CHECKED" if report else None
    missing_kernel_status = "NOT_RECORDED" if matched_by_path else missing_status
    panels = []
    kernel_entries, rule_entries = [], []
    witness = artifact.witness
    if witness is not None:
        rules = {rule.id: rule for rule in witness.rules}
        rule_links = {rule.id: f"rule-{i}" for i, rule in enumerate(witness.rules)}
        kernel_links = {boundary.name: f"kernel-{i}" for i, boundary in enumerate(witness.kernels)}
        rule_results = {item.rule: item for item in report.rules} if report else {}
        kernel_results = {item.kernel: item for item in report.kernels} if report else {}
        claims_by_kernel: dict[str, list[Claim]] = defaultdict(list)
        claims_by_rule: dict[str, list[Claim]] = defaultdict(list)
        for claim in witness.claims:
            claims_by_kernel[claim.kernel].append(claim)
            claims_by_rule[claim.rule].append(claim)

        snapshots = {}
        for projection, ir in (("source", artifact.source), ("target", artifact.target)):
            try:
                snapshots[projection] = parse_module(ir)
            except Exception:
                # A refuted witness still has recorded data edges and rule patterns.
                snapshots[projection] = None
        source_hosts = _host_tracks(snapshots["source"], claims_by_kernel, rules, "source")
        target_hosts = _host_tracks(snapshots["target"], claims_by_kernel, rules, "target")

        for i, boundary in enumerate(witness.kernels):
            name = boundary.name
            link = f"kernel-{i}"
            claims = claims_by_kernel[name]
            check = kernel_results.get(name)
            status = check.status if check else missing_kernel_status
            detail = escape(check.detail) if check else ""
            if report and not check:
                detail = "No claim graph verdict recorded for this kernel"
            used_rules = {claim.rule for claim in claims}
            rule_statuses = {
                rule: rule_results[rule].status if rule in rule_results else missing_status
                for rule in used_rules
            }
            checked_rules = sum(verdict == "VERIFIED" for verdict in rule_statuses.values())
            graph = _claim_graph(
                boundary, claims, witness, rules, rule_links,
                source_hosts.get(name, {}), target_hosts.get(name, {}), rule_statuses=rule_statuses,
            )
            rule_count = f"{checked_rules}/{len(used_rules)} rules verified" if report else ""
            graph_summary = " · ".join(filter(None, (f"{len(claims)} claims", rule_count)))
            check_detail = f"<p>{detail}</p>" if detail else ""
            coverage = f'<span class="rule-count muted">{rule_count}</span>' if rule_count else ""
            kernel_entries.append((link, f"@{name}", coverage))
            panels.append(f"""
<section class="panel" id="{link}" data-panel tabindex="-1">
  <h2>@{escape(name)}</h2>
  {check_detail}
  <div class="graph-heading">
    <div class="panel-heading"><h3>Claim graph structure</h3>{_status(status)}</div>
    <span class="muted">{graph_summary}</span>
  </div>
  {_rule_legend(set(rule_statuses.values()))}
  <div class="graph-frame" role="region" aria-label="Claim graph for @{escape(name)}" tabindex="0">
    {graph.svg(dot, f"{link}-graph")}
  </div>
</section>""")
        for i, rule in enumerate(witness.rules):
            link = f"rule-{i}"
            verdict = rule_results.get(rule.id)
            rule_entries.append((link, _rule_name(rule), _status(verdict.status if verdict else missing_status)))
            panels.append(_rule_panel(rule, verdict, claims_by_rule[rule.id], kernel_links, dot, link, missing_status))

    if not panels:
        panels.append('<p class="panel">This compilation step recorded no rules or kernels.</p>')
    template = Template(files("qstack.verification").joinpath("viewer.html").read_text(encoding="utf-8"))
    report_note = " · Matched using the report’s recorded artifact" if matched_by_path else ""
    html = template.substitute(
        filename=escape(artifact_path.name),
        summary=(
            f'<strong>Step verdict</strong> {_status(report.status)} '
            f'<span class="muted">· {escape(report.detail + report_note)}</span>'
            if report else '<span class="muted">Witness only</span>'
        ),
        available_backends=_available_backends(report),
        navigation=_navigation("Kernels", kernel_entries) + _navigation("Rules", rule_entries),
        panels="\n".join(panels),
    )
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a compilation step to Docket.")
    parser.add_argument("artifact", type=Path, help="saved qstack compilation step")
    parser.add_argument(
        "-o", "--output", type=Path, default=_DEFAULT_OUTPUT, help="HTML destination (default: %(default)s)",
    )
    parser.add_argument("--report", type=Path, help="saved verification report to overlay")
    args = parser.parse_args()
    try:
        output = generate_docket(args.artifact, args.output, report=args.report)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    print(output.resolve())


if __name__ == "__main__":
    main()
