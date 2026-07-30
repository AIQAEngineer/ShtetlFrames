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


def exclusions_path() -> Path:
    return clip_ft_dir() / "exclusions.json"


def load_exclusions() -> set[str]:
    """Relative paths like ``keep/cand_1.jpg`` marked excluded from training."""
    p = exclusions_path()
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return set()
    raw = data.get("excluded") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return set()
    out: set[str] = set()
    for item in raw:
        s = str(item or "").replace("\\", "/").lstrip("/")
        if s and ".." not in s:
            out.add(s)
    return out


def save_exclusions(excluded: set[str]) -> dict[str, Any]:
    clip_ft_dir().mkdir(parents=True, exist_ok=True)
    cleaned = sorted({str(x).replace("\\", "/").lstrip("/") for x in excluded if x})
    payload = {
        "excluded": cleaned,
        "n_excluded": len(cleaned),
        "updated_at": time.time(),
    }
    exclusions_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def set_excluded(paths: list[str], *, excluded: bool) -> dict[str, Any]:
    cur = load_exclusions()
    for raw in paths:
        rel = str(raw or "").replace("\\", "/").lstrip("/")
        if not rel or ".." in rel:
            continue
        if excluded:
            cur.add(rel)
        else:
            cur.discard(rel)
    meta = save_exclusions(cur)
    meta["ok"] = True
    return meta


def list_dataset_frames(
    *,
    label: str | None = None,
    included: bool | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    """List deep-sample frames with include/exclude state for the Probe UI."""
    root = dataset_dir()
    excluded = load_exclusions()
    labels = []
    if label in ("keep", "pass"):
        labels = [label]
    else:
        labels = ["keep", "pass"]

    items: list[dict[str, Any]] = []
    for lab in labels:
        d = root / lab
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.jpg")):
            if p.stat().st_size < 200:
                continue
            rel = f"{lab}/{p.name}".replace("\\", "/")
            is_in = rel not in excluded
            if included is True and not is_in:
                continue
            if included is False and is_in:
                continue
            cand_id = None
            time_sec = None
            name = p.stem
            # cand_123_still / cand_123_t01234 / cand_123
            if name.startswith("cand_"):
                rest = name[5:]
                if "_t" in rest:
                    cid_s, t_s = rest.split("_t", 1)
                    try:
                        cand_id = int(cid_s)
                    except ValueError:
                        cand_id = None
                    try:
                        time_sec = int(t_s) / 100.0
                    except ValueError:
                        time_sec = None
                elif rest.endswith("_still"):
                    try:
                        cand_id = int(rest[: -len("_still")])
                    except ValueError:
                        cand_id = None
                else:
                    try:
                        cand_id = int(rest.split("_")[0])
                    except ValueError:
                        cand_id = None
            items.append(
                {
                    "path": rel,
                    "label": lab,
                    "name": p.name,
                    "included": is_in,
                    "url": f"/media/clip_ft/{rel}",
                    "bytes": p.stat().st_size,
                    "cand_id": cand_id,
                    "time_sec": time_sec,
                }
            )

    total = len(items)
    offset = max(0, int(offset))
    limit = max(1, min(2000, int(limit)))
    page = items[offset : offset + limit]
    n_keep = sum(1 for i in items if i["label"] == "keep")
    n_pass = sum(1 for i in items if i["label"] == "pass")
    n_inc = sum(1 for i in items if i["included"])
    n_exc = total - n_inc
    return {
        "ok": True,
        "items": page,
        "total": total,
        "offset": offset,
        "limit": limit,
        "counts": {
            "keep": n_keep,
            "pass": n_pass,
            "included": n_inc,
            "excluded": n_exc,
            "keep_included": sum(
                1 for i in items if i["label"] == "keep" and i["included"]
            ),
            "pass_included": sum(
                1 for i in items if i["label"] == "pass" and i["included"]
            ),
        },
    }


def training_keep_pass_paths() -> tuple[list[Path], list[Path], dict[str, int]]:
    """Resolve Keep/Pass paths for training from include/exclude toggles.

    Semantics (Probe UI):
      - Included Keep  → positive (Keep)
      - Included Pass  → negative (wrong)
      - Excluded (any) → negative (wrong) — never ignored
    """
    root = dataset_dir()
    excluded = load_exclusions()
    keep_pos: list[Path] = []
    pass_neg: list[Path] = []
    stats = {
        "keep_included": 0,
        "pass_included": 0,
        "excluded_as_wrong": 0,
        "excluded_from_keep": 0,
        "excluded_from_pass": 0,
    }
    for lab in ("keep", "pass"):
        d = root / lab
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.jpg")):
            if p.stat().st_size < 200:
                continue
            rel = f"{lab}/{p.name}".replace("\\", "/")
            if rel in excluded:
                pass_neg.append(p)
                stats["excluded_as_wrong"] += 1
                if lab == "keep":
                    stats["excluded_from_keep"] += 1
                else:
                    stats["excluded_from_pass"] += 1
            elif lab == "keep":
                keep_pos.append(p)
                stats["keep_included"] += 1
            else:
                pass_neg.append(p)
                stats["pass_included"] += 1
    return keep_pos, pass_neg, stats


def _included_label_paths(label: str) -> list[Path]:
    """Deprecated helper — prefer ``training_keep_pass_paths``."""
    keep_pos, pass_neg, _ = training_keep_pass_paths()
    return keep_pos if label == "keep" else pass_neg


def probe_enabled() -> bool:
    flag = (os.environ.get("CLIP_PROBE") or "1").strip().lower()
    return flag not in ("0", "false", "off", "no", "none")


def _still_for_candidate(cand_id: int) -> Path | None:
    from still_store import candidate_crop_path, candidate_still_path

    for p in (candidate_crop_path(cand_id), candidate_still_path(cand_id)):
        if p.is_file() and p.stat().st_size > 200:
            return p
    return None


def _hit_sample_times(
    start_sec: float,
    end_sec: float,
    *,
    pad: float,
    step: float,
    max_frames: int,
) -> list[float]:
    """Dense times around a labeled hit window, capped at ``max_frames``."""
    start = max(0.0, float(start_sec))
    end = max(start, float(end_sec))
    mid = 0.5 * (start + end)
    step = max(0.2, float(step))
    pad = max(0.0, float(pad))
    t0 = max(0.0, start - pad)
    t1 = end + pad
    raw: list[float] = []
    t = t0
    while t <= t1 + 1e-9:
        raw.append(round(t, 3))
        t += step
    for must in (start, mid, end):
        m = round(float(must), 3)
        if m not in raw:
            raw.append(m)
    raw = sorted(set(raw))
    if len(raw) <= max_frames:
        return raw
    # Keep mid + even subsample
    mid_i = min(range(len(raw)), key=lambda i: abs(raw[i] - mid))
    idxs = {mid_i}
    n = max_frames - 1
    if n > 0:
        for i in range(n):
            idxs.add(int(round(i * (len(raw) - 1) / max(n, 1))))
    return [raw[i] for i in sorted(idxs)][:max_frames]


def _resolve_labeled_video(video_id: str, source_url: str) -> Path | None:
    """Local cache first, then download Pathé/source if needed."""
    from config import VIDEOS_DIR
    from media_files import VIDEO_EXTS

    vid = (video_id or "").strip()
    url = (source_url or "").strip()
    if vid and VIDEOS_DIR.is_dir():
        for p in VIDEOS_DIR.iterdir():
            if p.stem == vid and p.suffix.lower() in VIDEO_EXTS:
                return p
    if url:
        try:
            from frame_strip import _download_source

            aid = vid or "clip"
            return _download_source(url, aid, aid)
        except Exception:
            return None
    return None


def _extract_times_to_dir(
    video: Path, times: list[float], out_dir: Path, *, thumb_h: int = 336
) -> list[tuple[float, Path]]:
    """Grab frames at ``times`` (OpenCV, ffmpeg fallback via still_ensure)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    got: list[tuple[float, Path]] = []
    try:
        from frame_strip import _opencv_extract_times

        paired = _opencv_extract_times(video, times, out_dir, thumb_h=thumb_h)
        if paired:
            return paired
    except Exception:
        pass
    from still_ensure import extract_frame

    for i, t in enumerate(times):
        dest = out_dir / f"f_{i:04d}.jpg"
        if extract_frame(video, float(t), dest):
            got.append((float(t), dest))
    return got


def export_keep_pass_dataset_deep(
    *,
    on_status: OnStatus = None,
    min_keep: int = MIN_KEEP,
    min_pass: int = MIN_PASS,
    keep_pad: float = 2.0,
    keep_step: float = 1.0,
    keep_max: int = 7,
    pass_pad: float = 4.0,
    pass_step: float = 0.75,
    pass_max: int = 12,
    thumb_h: int = 336,
) -> dict[str, Any]:
    """Deep-sample frames from Keep/Pass hit windows into clip_ft/dataset.

    Pass videos are sampled denser/longer to mine hard negatives. Groups by
    ``video_id`` so each reel is opened once.
    """
    import tempfile

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
            "SELECT id, decision, notes, video_id, source_url, start_sec, end_sec, "
            "peak_score FROM candidates WHERE decision IN ('accept','reject') "
            "ORDER BY video_id, start_sec, id"
        ).fetchall()

    by_video: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        d = dict(r)
        key = str(d.get("video_id") or d.get("source_url") or f"id_{d['id']}")
        by_video.setdefault(key, []).append(d)

    manifest: list[dict[str, Any]] = []
    n_keep = 0
    n_pass = 0
    n_videos = 0
    n_video_fail = 0

    for vi, (vid_key, items) in enumerate(by_video.items(), start=1):
        if on_status and (vi == 1 or vi % 5 == 0 or vi == len(by_video)):
            on_status(
                f"Deep sample {vi}/{len(by_video)} reels · "
                f"keep_frames={n_keep} pass_frames={n_pass}"
            )
        url = str(items[0].get("source_url") or "")
        video_id = str(items[0].get("video_id") or vid_key)
        video = _resolve_labeled_video(video_id, url)
        if video is None:
            n_video_fail += 1
            # Fall back to single still per candidate
            for d in items:
                cid = int(d["id"])
                src = _still_for_candidate(cid)
                if src is None:
                    continue
                label = "keep" if d["decision"] == "accept" else "pass"
                dest = (keep_dir if label == "keep" else pass_dir) / f"cand_{cid}.jpg"
                shutil.copy2(src, dest)
                if label == "keep":
                    n_keep += 1
                else:
                    n_pass += 1
                manifest.append(
                    {
                        "id": cid,
                        "decision": d["decision"],
                        "label": label,
                        "path": str(dest.relative_to(root)).replace("\\", "/"),
                        "source": "still_fallback",
                        "video_id": video_id,
                    }
                )
            continue

        n_videos += 1
        with tempfile.TemporaryDirectory(prefix="clip_deep_") as td:
            work = Path(td)
            for d in items:
                cid = int(d["id"])
                decision = str(d.get("decision") or "")
                label = "keep" if decision == "accept" else "pass"
                start = float(d.get("start_sec") or 0.0)
                end = float(d.get("end_sec") or start)
                if label == "keep":
                    times = _hit_sample_times(
                        start, end, pad=keep_pad, step=keep_step, max_frames=keep_max
                    )
                else:
                    times = _hit_sample_times(
                        start, end, pad=pass_pad, step=pass_step, max_frames=pass_max
                    )
                # Always try to include the curated still first
                still = _still_for_candidate(cid)
                dest_dir = keep_dir if label == "keep" else pass_dir
                if still is not None:
                    dest = dest_dir / f"cand_{cid}_still.jpg"
                    shutil.copy2(still, dest)
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
                            "source": "labeled_still",
                            "video_id": video_id,
                            "time_sec": None,
                        }
                    )
                cand_work = work / f"c{cid}"
                paired = _extract_times_to_dir(
                    video, times, cand_work, thumb_h=thumb_h
                )
                for t, fp in paired:
                    dest = dest_dir / f"cand_{cid}_t{int(round(t * 100)):05d}.jpg"
                    shutil.copy2(fp, dest)
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
                            "source": "deep_frame",
                            "video_id": video_id,
                            "time_sec": t,
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
        "n_videos_ok": n_videos,
        "n_videos_fail": n_video_fail,
        "deep": True,
        "exported_at": time.time(),
        "root": str(root),
        "keep_pad": keep_pad,
        "pass_pad": pass_pad,
        "keep_max": keep_max,
        "pass_max": pass_max,
    }
    (root / "manifest.json").write_text(
        json.dumps({"meta": meta, "items": manifest}, indent=2),
        encoding="utf-8",
    )
    if on_status:
        on_status(
            f"Deep export · {n_keep} Keep + {n_pass} Pass frames "
            f"from {n_videos} reels ({n_video_fail} still-only)"
        )
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
    keep_paths, pass_paths, sel = training_keep_pass_paths()
    n_excl = int(sel.get("excluded_as_wrong") or 0)
    if len(keep_paths) < MIN_KEEP:
        return {
            "ok": False,
            "error": f"need_at_least_{MIN_KEEP}_keeps_have_{len(keep_paths)}",
            "n_excluded_as_wrong": n_excl,
            "selection": sel,
        }
    if len(pass_paths) < MIN_PASS:
        return {
            "ok": False,
            "error": f"need_at_least_{MIN_PASS}_pass_have_{len(pass_paths)}",
            "n_excluded_as_wrong": n_excl,
            "selection": sel,
        }

    train_items, val_items = _stratified_split(keep_paths, pass_paths)
    if on_status:
        on_status(
            f"Training probe · train={len(train_items)} val={len(val_items)} "
            f"(keep={len(keep_paths)} wrong={len(pass_paths)}"
            + (f", excluded→wrong={n_excl}" if n_excl else "")
            + ")"
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
    train_x = torch.stack([embed(p) for p, _ in train_items]).to(dev)
    train_y = torch.tensor([y for _, y in train_items], dtype=torch.float32, device=dev)
    val_x = (
        torch.stack([embed(p) for p, _ in val_items]).to(dev)
        if val_items
        else train_x[:1]
    )
    val_y = (
        torch.tensor([y for _, y in val_items], dtype=torch.float32, device=dev)
        if val_items
        else train_y[:1]
    )

    dim = int(train_x.shape[-1])
    head = nn.Linear(dim, 1).to(dev)
    n_pos = float((train_y >= 0.5).sum().item())
    n_neg = float(len(train_y) - n_pos)
    pos_weight = torch.tensor([n_neg / max(n_pos, 1.0)], device=dev)
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
            auc = _binary_auc(v_prob.detach().cpu().tolist(), val_y.detach().cpu().tolist())
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


def export_and_train(
    *,
    on_status: OnStatus = None,
    deep: bool = False,
    device: str | None = None,
) -> dict[str, Any]:
    if deep:
        exp = export_keep_pass_dataset_deep(on_status=on_status)
    else:
        exp = export_keep_pass_dataset(on_status=on_status)
    if not exp.get("ok"):
        return exp
    result = train_linear_probe(on_status=on_status, device=device)
    result["export"] = {k: v for k, v in exp.items() if k != "ok"}
    return result


def start_clip_ft_job(*, deep: bool = True, export: bool = True) -> dict[str, Any]:
    """Background job id=clip_ft: export + train + push probe to pods.

    ``export=False`` trains on the existing dataset (respecting exclusions).
    """
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
        phase="export" if export else "train",
        message=(
            "Deep-sampling Keep/Pass frames…"
            if export and deep
            else ("Exporting Keep/Pass stills…" if export else "Training from included frames…")
        ),
        progress=5,
        error="",
        hits=0,
    )

    def _run() -> None:
        global _job_running
        try:

            def status(msg: str) -> None:
                set_job("clip_ft", message=str(msg)[:200])

            exp: dict[str, Any] = {"ok": True}
            if export:
                set_job(
                    "clip_ft",
                    phase="export",
                    progress=15,
                    message="Deep-sampling frames…" if deep else "Exporting stills…",
                )
                if deep:
                    exp = export_keep_pass_dataset_deep(on_status=status)
                else:
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
                    f"Training · {exp.get('n_keep', '?')} Keep / {exp.get('n_pass', '?')} Pass frames"
                    if export
                    else "Training included Keep/Pass frames…"
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
