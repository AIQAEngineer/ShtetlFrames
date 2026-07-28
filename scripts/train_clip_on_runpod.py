"""Train CLIP linear probe on a RunPod GPU after local deep export.

1. Deep-export dataset locally (if missing)
2. ensure_pods(min_ready=1)
3. Sync train helper to the pod
4. Upload dataset images (batched base64)
5. Train on CUDA, pull probe.pt back, install locally + push to fleet
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BATCH = 40


def _status(msg: str) -> None:
    print(msg, flush=True)


def _ensure_dataset() -> Path:
    from clip_ft import dataset_dir, export_keep_pass_dataset_deep

    root = dataset_dir()
    keep_n = len(list((root / "keep").glob("*.jpg"))) if (root / "keep").is_dir() else 0
    pass_n = len(list((root / "pass").glob("*.jpg"))) if (root / "pass").is_dir() else 0
    if keep_n >= 8 and pass_n >= 3:
        _status(f"Using existing dataset keep={keep_n} pass={pass_n}")
        return root
    _status("Deep-exporting Keep/Pass frames…")
    exp = export_keep_pass_dataset_deep(on_status=_status)
    if not exp.get("ok"):
        raise SystemExit(json.dumps(exp))
    return root


def _pod_base() -> str:
    from config import load_env
    from runpod_client import get_pod_pool
    from runpod_provision import ensure_pods, find_shtetl_pods, pod_proxy_url

    load_env()
    pool = get_pod_pool()
    if pool:
        return pool[0].rstrip("/")
    _status("Provisioning 1 GPU pod for training…")
    bases = ensure_pods(count=1, min_ready=1, on_status=_status)
    if bases:
        return bases[0].rstrip("/")
    pods = find_shtetl_pods()
    for p in pods:
        pid = p.get("id")
        if pid:
            return pod_proxy_url(pid).rstrip("/")
    raise RuntimeError("no_gpu_pod")


def _sync_train_module(base: str) -> None:
    files = {
        "clip_ft_remote_train.py": (
            ROOT / "runpod_worker" / "clip_ft_remote_train.py"
        ).read_text(encoding="utf-8"),
        "entry.py": (ROOT / "runpod_worker" / "entry.py").read_text(encoding="utf-8"),
    }
    r = requests.post(f"{base}/sync_push", json={"files": files}, timeout=180)
    _status(f"sync_push train modules http={r.status_code} body={(r.text or '')[:160]}")
    # Hot reload routes
    try:
        requests.post(f"{base}/reload", json={}, timeout=60)
    except Exception:
        pass


def main() -> None:
    from clip_ft import clip_ft_dir, probe_path

    root = _ensure_dataset()
    base = _pod_base()
    _status(f"Training on pod {base}")
    _sync_train_module(base)

    # Prefer dedicated endpoint (must exist on pod after sync/reload)
    keep_files = sorted((root / "keep").glob("*.jpg"))
    pass_files = sorted((root / "pass").glob("*.jpg"))
    _status(f"Uploading {len(keep_files)} keep + {len(pass_files)} pass frames…")

    def batches(paths: list[Path], label: str):
        for i in range(0, len(paths), BATCH):
            chunk = paths[i : i + BATCH]
            items = []
            for p in chunk:
                items.append(
                    {
                        "name": p.name,
                        "label": label,
                        "b64": base64.b64encode(p.read_bytes()).decode("ascii"),
                    }
                )
            yield items

    # Clear remote staging
    requests.post(f"{base}/clip_ft_train", json={"op": "reset"}, timeout=60)

    for items in batches(keep_files, "keep"):
        r = requests.post(
            f"{base}/clip_ft_train", json={"op": "add", "items": items}, timeout=180
        )
        if r.status_code == 404:
            raise SystemExit(
                "Pod missing /clip_ft_train — sync entry.py with the new endpoint "
                "or restart the pod after pulling latest worker."
            )
        r.raise_for_status()
        _status(f"  uploaded keep batch · {r.json()}")
    for items in batches(pass_files, "pass"):
        r = requests.post(
            f"{base}/clip_ft_train", json={"op": "add", "items": items}, timeout=180
        )
        r.raise_for_status()
        _status(f"  uploaded pass batch · {r.json()}")

    _status("Starting CUDA train on pod…")
    r = requests.post(
        f"{base}/clip_ft_train",
        json={"op": "train", "epochs": 80},
        timeout=1800,
    )
    r.raise_for_status()
    body = r.json()
    if not body.get("ok"):
        raise SystemExit(json.dumps(body)[:800])
    b64 = body.get("probe_b64") or ""
    if not b64:
        raise SystemExit("no_probe_b64")
    raw = base64.b64decode(b64)
    out = probe_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    metrics = {k: v for k, v in body.items() if k != "probe_b64"}
    (clip_ft_dir() / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    _status(f"Saved probe ({len(raw)} bytes) → {out}")
    _status(json.dumps(metrics, indent=2))

    try:
        from runpod_client import push_clip_probe_to_pods

        push = push_clip_probe_to_pods(force=True, on_status=_status)
        _status(f"Fleet push: {push}")
    except Exception as e:
        _status(f"Fleet push skipped: {e}")


if __name__ == "__main__":
    main()
