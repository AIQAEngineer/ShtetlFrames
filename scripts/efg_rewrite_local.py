"""CLI wrapper for offline EFG resolve rewrite."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from efg_rewrite import run_rewrite


def main() -> int:
    try:
        stats = run_rewrite()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
