"""Command-line interface for checking a serialized circuit rule."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quivalence import verify_rule


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare the matrices of one circuit rule")
    parser.add_argument("rule", type=Path, help="JSON file containing one rule object")
    args = parser.parse_args()
    result = verify_rule(json.loads(args.rule.read_text(encoding="utf-8")))
    print(json.dumps(result, sort_keys=True))
    return {"VERIFIED": 0, "REFUTED": 1, "UNSUPPORTED": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
