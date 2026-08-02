"""Stage labeled Keep/Pass stills on one pod and train the CLIP linear probe.

Usage: _probe_train_remote.py <pod_base_url>
Saves the returned probe to output/clip_ft/probe.pt and the runpod_worker mirror.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests  # noqa: E402
from db import db, init_db  # noqa: E402
from clip_ft import _still_for_candidate  # noqa: E402

BATCH = 30
EPOCHS = 80


def gather_items() -> list[dict]:
    init_db()
    with db() as conn:
        rows = conn.execute(
            "SELECT id, decision FROM candidates "
            "WHERE decision IN ('accept','reject') ORDER BY id"
        ).fetchall()
    items = []
    for r in rows:
        cid = int(r["id"])
        p = _still_for_candidate(cid)
        if p is None:
            continue
        label = "keep" if r["decision"] == "accept" else "pass"
        items.append(
            {
                "name": f"cand_{cid}.jpg",
                "label": label,
                "b64": base64.b64encode(p.read_bytes()).decode("ascii"),
            }
        )
    return items


def main() -> None:
    base = sys.argv[1].rstrip("/")
    items = gather_items()
    n_keep = sum(1 for it in items if it["label"] == "keep")
    n_pass = sum(1 for it in items if it["label"] == "pass")
    print(f"[train] staging {len(items)} items (keep={n_keep} pass={n_pass}) on {base}")

    # Pods sync worker code from GitHub but worker_sync._SYNC_FILES omits
    # clip_ft_remote_train.py — push it via the whitelisted sync_push route.
    trainer = ROOT / "runpod_worker" / "clip_ft_remote_train.py"
    r = requests.post(
        f"{base}/sync_push",
        json={"files": {"clip_ft_remote_train.py": trainer.read_text(encoding="utf-8")}},
        timeout=120,
    )
    body = r.json() if r.content else {}
    print(f"[train] sync_push trainer -> {r.status_code} {json.dumps(body)[:300]}")
    if r.status_code != 200 or not body.get("ok"):
        print("[train] trainer module push FAILED")
        sys.exit(1)

    r = requests.post(f"{base}/clip_ft_train", json={"op": "reset"}, timeout=60)
    print(f"[train] reset -> {r.status_code} {r.text[:200]}")
    body = r.json() if r.content else {}
    if r.status_code != 200 or not body.get("ok"):
        print("[train] reset FAILED")
        sys.exit(2)

    staged_keep = staged_pass = 0
    for i in range(0, len(items), BATCH):
        chunk = items[i : i + BATCH]
        r = requests.post(
            f"{base}/clip_ft_train",
            json={"op": "add", "items": chunk},
            timeout=180,
        )
        body = r.json() if r.content else {}
        if r.status_code != 200 or not body.get("ok"):
            print(f"[train] add batch {i // BATCH} FAILED: {r.status_code} {r.text[:300]}")
            sys.exit(2)
        staged_keep = body.get("n_keep", staged_keep)
        staged_pass = body.get("n_pass", staged_pass)
        print(
            f"[train] add batch {i // BATCH + 1}: added={body.get('added')} "
            f"totals keep={staged_keep} pass={staged_pass}"
        )

    print(f"[train] starting train epochs={EPOCHS} ...")
    r = requests.post(
        f"{base}/clip_ft_train",
        json={"op": "train", "epochs": EPOCHS},
        timeout=600,
    )
    body = r.json() if r.content else {}
    if r.status_code != 200 or not body.get("ok"):
        print(f"[train] train FAILED: {r.status_code} {r.text[:500]}")
        sys.exit(3)

    probe_b64 = body.get("probe_b64") or ""
    raw = base64.b64decode(probe_b64)
    out_dir = ROOT / "output" / "clip_ft"
    out_dir.mkdir(parents=True, exist_ok=True)
    probe_path = out_dir / "probe.pt"
    probe_path.write_bytes(raw)
    mirror = ROOT / "runpod_worker" / "clip_ft" / "probe.pt"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_bytes(raw)

    metrics = {k: v for k, v in body.items() if k != "probe_b64"}
    metrics["local_probe"] = str(probe_path)
    metrics["local_bytes"] = len(raw)
    (out_dir / "remote_train_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
