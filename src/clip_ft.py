"""Export Keep/Pass stills and train a frozen-CLIP linear probe."""

from __future__ import annotations

import json
import os
import random
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable

import torch
import torch.nn as nn
from PIL import Image

OnStatus = Callable[[str], None] | None

MIN_KEEP = 8
# Golden FP stills are typically 3; human Pass labels raise this further.
MIN_PASS = 3
VAL_FRACTION = 0.2
DEFAULT_EPOCHS = 80
DEFAULT_LR = 0.05
EARLY_STOP_PATIENCE = 12

_job_lock = threading.Lock()
_job_running = False


def clip_ft_dir() -> Path:
    try:
        from config import OUTPUT_DIR

        return OUTPUT_DIR / "clip_ft"
    except Exception:
        return Path(__file__).resolve().parents[1] / "output" / "clip_ft"


def probe_path() -> Path:
    env = (os.environ.get("CLIP_PROBE_PATH") or "").strip()
    if env:
        return Path(env)
    return clip_ft_dir() / "probe.pt"


def dataset_dir() -> Path:
    return clip_ft_dir() / "dataset"


def probe_enabled() -> bool:
    flag = (os.environ.get("CLIP_PROBE") or "1").strip().lower()
    return flag not in ("0", "false", "off", "no", "none")


def _still_for_candidate(cand_id: int) -> Path | None:
    from still_store import candidate_crop_path, candidate_still_path

    for p in (candidate_crop_path(cand_id), candidate_still_path(cand_id)):
        if p.is_file() and p.stat().st_size > 200:
            return p
    return None


def _golden_pass_paths() -> list[Path]:
    try:
        from config import ROOT
    except Exception:
        ROOT = Path(__file__).resolve().parents[1]
    return [
        ROOT / "output" / "contact_sheets" / "cand_1825.jpg",
        ROOT / "output" / "contact_sheets" / "cand_1806.jpg",
        ROOT / "output" / "contact_sheets" / "cand_1831.jpg",
    ]


def export_keep_pass_dataset(
    *,
    on_status: OnStatus = None,
    min_keep: int = MIN_KEEP,
    min_pass: int = MIN_PASS,
) -> dict[str, Any]:
    """Copy labeled candidate stills into output/clip_ft/dataset/{keep,pass}/."""
    from db import db, init_db

    init_db()
    root = dataset_dir()
    keep_dir = root / "keep"
    pass_dir = root / "pass"
    if root.exists():
        shutil.rmtree(root)
    keep_dir.mkdir(parents=True, exist_ok=True)
    pass_dir.mkdir(parents=True, exist_ok=True)

    with db() as conn:
        rows = conn.execute(
            "SELECT id, decision, notes, video_id, source_url, peak_score "
            "FROM candidates WHERE decision IN ('accept','reject') ORDER BY id"
        ).fetchall()

    manifest: list[dict[str, Any]] = []
    n_keep = 0
    n_pass = 0
    for r in rows:
        d = dict(r)
        cid = int(d["id"])
        decision = str(d.get("decision") or "").strip()
        src = _still_for_candidate(cid)
        if src is None:
            continue
        label = "keep" if decision == "accept" else "pass"
        dest = (keep_dir if label == "keep" else pass_dir) / f"cand_{cid}.jpg"
        shutil.copy2(src, dest)
        if label == "keep":
            n_keep += 1
        else:
            n_pass += 1
        manifest.append(
            {
                "id": cid,
                "decision": decision,
                "label": label,
                "path": str(dest.relative_to(root)).replace("\\", "/"),
                "notes": str(d.get("notes") or "")[:240],
                "video_id": d.get("video_id"),
                "source": "candidates",
            }
        )

    if n_pass < min_pass:
        for i, gp in enumerate(_golden_pass_paths()):
            if n_pass >= min_pass:
                break
            if not gp.is_file() or gp.stat().st_size < 200:
                continue
            dest = pass_dir / f"golden_pass_{i}.jpg"
            shutil.copy2(gp, dest)
            n_pass += 1
            manifest.append(
                {
                    "id": -(9100 + i),
                    "decision": "reject",
                    "label": "pass",
                    "path": str(dest.relative_to(root)).replace("\\", "/"),
                    "notes": "golden pass (pad)",
                    "video_id": "golden_pathe_fp",
                    "source": "golden",
                }
            )

    meta = {
        "n_keep": n_keep,
        "n_pass": n_pass,
        "n_total": n_keep + n_pass,
        "exported_at": time.time(),
        "root": str(root),
    }
    (root / "manifest.json").write_text(
        json.dumps({"meta": meta, "items": manifest}, indent=2),
        encoding="utf-8",
    )
    if on_status:
        on_status(f"Exported {n_keep} Keep + {n_pass} Pass stills")

    if n_keep < min_keep:
        return {
            "ok": False,
            "error": f"need_at_least_{min_keep}_keeps_have_{n_keep}",
            **meta,
        }
    if n_pass < min_pass:
        return {
            "ok": False,
            "error": f"need_at_least_{min_pass}_pass_have_{n_pass}",
            **meta,
        }
    return {"ok": True, **meta, "manifest_items": len(manifest)}


def _stratified_split(
    keep_paths: list[Path], pass_paths: list[Path], *, seed: int = 42
) -> tuple[list[tuple[Path, float]], list[tuple[Path, float]]]:
    rng = random.Random(seed)
    keep = list(keep_paths)
    pas = list(pass_paths)
    rng.shuffle(keep)
    rng.shuffle(pas)

    def split(xs: list[Path]) -> tuple[list[Path], list[Path]]:
        if len(xs) <= 1:
            return xs, []
        n_val = max(1, int(round(len(xs) * VAL_FRACTION)))
        n_val = min(n_val, len(xs) - 1)
        return xs[n_val:], xs[:n_val]

    keep_tr, keep_va = split(keep)
    pass_tr, pass_va = split(pas)
    train = [(p, 1.0) for p in keep_tr] + [(p, 0.0) for p in pass_tr]
    val = [(p, 1.0) for p in keep_va] + [(p, 0.0) for p in pass_va]
    rng.shuffle(train)
    rng.shuffle(val)
    if not val:
        val = []
        if keep_tr:
            val.append((keep_tr[0], 1.0))
            train = [(p, y) for p, y in train if p != keep_tr[0]]
        if pass_tr:
            val.append((pass_tr[0], 0.0))
            train = [(p, y) for p, y in train if p != pass_tr[0]]
    return train, val


def _binary_auc(scores: list[float], labels: list[float]) -> float | None:
    pairs = sorted(zip(scores, labels), key=lambda t: t[0])
    n_pos = sum(1 for _, y in pairs if y >= 0.5)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    rank_sum = 0.0
    for i, (_, y) in enumerate(pairs, start=1):
        if y >= 0.5:
            rank_sum += i
    return float((rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def train_linear_probe(
    *,
    on_status: OnStatus = None,
    epochs: int = DEFAULT_EPOCHS,
    lr: float = DEFAULT_LR,
    device: str | None = None,
) -> dict[str, Any]:
    """Train linear head on frozen OpenCLIP embeddings; write probe.pt + metrics.json."""
    import open_clip

    from shtetl_core.cues import CLIP_MODEL, CLIP_PRETRAINED

    root = dataset_dir()
    keep_dir = root / "keep"
    pass_dir = root / "pass"
    keep_paths = sorted(p for p in keep_dir.glob("*.jpg") if p.stat().st_size > 200)
    pass_paths = sorted(p for p in pass_dir.glob("*.jpg") if p.stat().st_size > 200)
    if len(keep_paths) < MIN_KEEP:
        return {
            "ok": False,
            "error": f"need_at_least_{MIN_KEEP}_keeps_have_{len(keep_paths)}",
        }
    if len(pass_paths) < MIN_PASS:
        return {
            "ok": False,
            "error": f"need_at_least_{MIN_PASS}_pass_have_{len(pass_paths)}",
        }

    train_items, val_items = _stratified_split(keep_paths, pass_paths)
    if on_status:
        on_status(
            f"Training probe · train={len(train_items)} val={len(val_items)} "
            f"(keep={len(keep_paths)} pass={len(pass_paths)})"
        )

    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model, _, preprocess = open_clip.create_model_and_transforms(
        CLIP_MODEL, pretrained=CLIP_PRETRAINED
    )
    model = model.to(dev).eval()
    for p in model.parameters():
        p.requires_grad_(False)

    @torch.no_grad()
    def embed(path: Path) -> torch.Tensor:
        img = Image.open(path).convert("RGB")
        t = preprocess(img).unsqueeze(0).to(dev)
        feat = model.encode_image(t)
        feat = feat / feat.norm(dim=-1, keepdim=True)
        return feat.squeeze(0).float().cpu()

    if on_status:
        on_status("Encoding stills with frozen CLIP…")
    train_x = torch.stack([embed(p) for p, _ in train_items])
    train_y = torch.tensor([y for _, y in train_items], dtype=torch.float32)
    val_x = torch.stack([embed(p) for p, _ in val_items]) if val_items else train_x[:1]
    val_y = (
        torch.tensor([y for _, y in val_items], dtype=torch.float32)
        if val_items
        else train_y[:1]
    )

    dim = int(train_x.shape[-1])
    head = nn.Linear(dim, 1)
    n_pos = float((train_y >= 0.5).sum().item())
    n_neg = float(len(train_y) - n_pos)
    pos_weight = torch.tensor([n_neg / max(n_pos, 1.0)])
    opt = torch.optim.Adam(head.parameters(), lr=lr)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    best_state: dict[str, Any] | None = None
    best_auc = -1.0
    best_acc = -1.0
    stale = 0
    history: list[dict[str, Any]] = []

    for epoch in range(1, epochs + 1):
        head.train()
        opt.zero_grad()
        logits = head(train_x).squeeze(-1)
        loss = loss_fn(logits, train_y)
        loss.backward()
        opt.step()

        head.eval()
        with torch.no_grad():
            v_logits = head(val_x).squeeze(-1)
            v_prob = torch.sigmoid(v_logits)
            v_pred = (v_prob >= 0.5).float()
            acc = float((v_pred == val_y).float().mean().item())
            auc = _binary_auc(v_prob.tolist(), val_y.tolist())
            metric = auc if auc is not None else acc
        history.append(
            {
                "epoch": epoch,
                "loss": float(loss.item()),
                "val_acc": acc,
                "val_auc": auc,
            }
        )
        improved = metric > best_auc + 1e-4
        if improved:
            best_auc = float(metric)
            best_acc = acc
            best_state = {
                k: v.detach().cpu().clone() for k, v in head.state_dict().items()
            }
            stale = 0
        else:
            stale += 1
        if on_status and (epoch == 1 or epoch % 10 == 0 or improved):
            on_status(
                f"epoch {epoch}/{epochs} · loss={loss.item():.3f} "
                f"val_acc={acc:.2f} val_auc={auc if auc is not None else 'n/a'}"
            )
        if stale >= EARLY_STOP_PATIENCE:
            break

    if best_state is None:
        best_state = {k: v.detach().cpu().clone() for k, v in head.state_dict().items()}

    out_dir = clip_ft_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_probe = out_dir / "probe.pt"
    payload = {
        "state_dict": best_state,
        "dim": dim,
        "clip_model": CLIP_MODEL,
        "clip_pretrained": CLIP_PRETRAINED,
        "blend": 0.5,
        "trained_at": time.time(),
        "n_keep": len(keep_paths),
        "n_pass": len(pass_paths),
        "val_auc": best_auc if best_auc >= 0 else None,
        "val_acc": best_acc if best_acc >= 0 else None,
    }
    torch.save(payload, out_probe)
    metrics = {
        "ok": True,
        "probe_path": str(out_probe),
        "n_keep": len(keep_paths),
        "n_pass": len(pass_paths),
        "n_train": len(train_items),
        "n_val": len(val_items),
        "val_auc": payload["val_auc"],
        "val_acc": payload["val_acc"],
        "epochs_ran": len(history),
        "device": dev,
        "history": history[-20:],
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    try:
        from config import ROOT

        mirror = ROOT / "runpod_worker" / "clip_ft" / "probe.pt"
        mirror.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out_probe, mirror)
        metrics["worker_mirror"] = str(mirror)
    except Exception:
        pass
    if on_status:
        on_status(
            f"Probe saved · val_acc={best_acc:.2f} "
            f"val_auc={best_auc if best_auc >= 0 else 'n/a'}"
        )
    return metrics


def export_and_train(*, on_status: OnStatus = None) -> dict[str, Any]:
    exp = export_keep_pass_dataset(on_status=on_status)
    if not exp.get("ok"):
        return exp
    return train_linear_probe(on_status=on_status)


def start_clip_ft_job() -> dict[str, Any]:
    """Background job id=clip_ft: export + train + push probe to pods."""
    global _job_running
    from db import get_job, init_db, set_job

    init_db()
    # Ensure job row exists (UPDATE no-ops on missing id).
    from db import db

    with db(write=True) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO jobs (id, status, phase, updated_at) "
            "VALUES ('clip_ft', 'idle', 'idle', ?)",
            (time.time(),),
        )
    with _job_lock:
        cur = get_job("clip_ft") or {}
        if _job_running or cur.get("status") == "running":
            return {
                "ok": False,
                "error": "clip_ft already running",
                "job": cur,
            }
        _job_running = True

    set_job(
        "clip_ft",
        status="running",
        phase="export",
        message="Exporting Keep/Pass stills…",
        progress=5,
        error="",
        hits=0,
    )

    def _run() -> None:
        global _job_running
        try:

            def status(msg: str) -> None:
                set_job("clip_ft", message=str(msg)[:200])

            set_job("clip_ft", phase="export", progress=15, message="Exporting stills…")
            exp = export_keep_pass_dataset(on_status=status)
            if not exp.get("ok"):
                set_job(
                    "clip_ft",
                    status="error",
                    phase="error",
                    message=str(exp.get("error") or "export_failed")[:200],
                    error=str(exp.get("error") or "")[:500],
                    progress=100,
                )
                return
            set_job(
                "clip_ft",
                phase="train",
                progress=40,
                hits=int(exp.get("n_keep") or 0),
                message=(
                    f"Training · {exp.get('n_keep')} Keep / {exp.get('n_pass')} Pass"
                ),
            )
            result = train_linear_probe(on_status=status)
            if not result.get("ok"):
                set_job(
                    "clip_ft",
                    status="error",
                    phase="error",
                    message=str(result.get("error") or "train_failed")[:200],
                    error=str(result.get("error") or "")[:500],
                    progress=100,
                )
                return
            set_job(
                "clip_ft",
                phase="push",
                progress=85,
                message="Pushing probe to GPU pods…",
            )
            pushed = 0
            try:
                from runpod_client import push_clip_probe_to_pods

                push = push_clip_probe_to_pods(on_status=status)
                pushed = int(push.get("pushed") or 0)
            except Exception as e:
                status(f"pod push skipped: {e}"[:160])
            auc = result.get("val_auc")
            acc = result.get("val_acc")
            msg = (
                f"CLIP probe ready · keep={result.get('n_keep')} "
                f"pass={result.get('n_pass')} val_acc={float(acc or 0):.2f}"
            )
            if isinstance(auc, (int, float)):
                msg += f" auc={float(auc):.2f}"
            if pushed:
                msg += f" · pods={pushed}"
            set_job(
                "clip_ft",
                status="done",
                phase="done",
                progress=100,
                hits=int(result.get("n_keep") or 0),
                message=msg[:200],
            )
        except Exception as e:
            set_job(
                "clip_ft",
                status="error",
                phase="error",
                message=str(e)[:200],
                error=str(e)[:800],
                progress=100,
            )
        finally:
            with _job_lock:
                _job_running = False

    threading.Thread(target=_run, name="clip-ft-train", daemon=True).start()
    return {"ok": True, "job": get_job("clip_ft")}
