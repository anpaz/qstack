"""Command-line entry point for Docket."""

from __future__ import annotations

import argparse
from pathlib import Path

from qstack.verification.docket import _DEFAULT_OUTPUT, generate_docket as generate_docket


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a compilation step to Docket.")
    parser.add_argument("artifact", type=Path, help="saved qstack compilation step")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="HTML destination (default: %(default)s)",
    )
    reports = parser.add_mutually_exclusive_group()
    reports.add_argument(
        "--report",
        type=Path,
        help="use a saved report instead of running verification",
    )
    reports.add_argument(
        "--witness-only",
        action="store_true",
        help="export without verification verdicts",
    )
    args = parser.parse_args()
    try:
        generate_docket(args.artifact, args.output, report=args.report, witness_only=args.witness_only)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    print(Path(args.output).resolve())


if __name__ == "__main__":
    main()
