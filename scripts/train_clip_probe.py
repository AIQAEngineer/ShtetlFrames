"""CLI: export Keep/Pass stills and train frozen-CLIP linear probe."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clip_ft import export_and_train  # noqa: E402


def main() -> None:
    def status(msg: str) -> None:
        print(msg, flush=True)

    result = export_and_train(on_status=status)
    print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
