"""GPU-side Keep/Pass CLIP linear probe trainer (loaded by entry /clip_ft_train)."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

STAGE = Path(__file__).resolve().parent / "clip_ft_stage"


def reset_stage() -> dict[str, Any]:
    import shutil

    if STAGE.exists():
        shutil.rmtree(STAGE)
    (STAGE / "keep").mkdir(parents=True, exist_ok=True)
    (STAGE / "pass").mkdir(parents=True, exist_ok=True)
    return {"ok": True, "stage": str(STAGE)}


def add_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    (STAGE / "keep").mkdir(parents=True, exist_ok=True)
    (STAGE / "pass").mkdir(parents=True, exist_ok=True)
    n = 0
    for it in items or []:
        label = str(it.get("label") or "").strip().lower()
        if label not in ("keep", "pass", "accept", "reject"):
            continue
        folder = "keep" if label in ("keep", "accept") else "pass"
        name = Path(str(it.get("name") or f"f_{n}.jpg")).name
        b64 = str(it.get("b64") or "")
        if not b64:
            continue
        raw = base64.b64decode(b64)
        if len(raw) < 200:
            continue
        (STAGE / folder / name).write_bytes(raw)
        n += 1
    return {
        "ok": True,
        "added": n,
        "n_keep": len(list((STAGE / "keep").glob("*.jpg"))),
        "n_pass": len(list((STAGE / "pass").glob("*.jpg"))),
    }


def train(*, epochs: int = 80, lr: float = 0.05) -> dict[str, Any]:
    import random

    import open_clip
    import torch
    import torch.nn as nn
    from PIL import Image

    keep_paths = sorted(p for p in (STAGE / "keep").glob("*.jpg") if p.stat().st_size > 200)
    pass_paths = sorted(p for p in (STAGE / "pass").glob("*.jpg") if p.stat().st_size > 200)
    if len(keep_paths) < 8:
        return {"ok": False, "error": f"need_keeps_have_{len(keep_paths)}"}
    if len(pass_paths) < 3:
        return {"ok": False, "error": f"need_pass_have_{len(pass_paths)}"}

    try:
        from shtetl_core.cues import CLIP_MODEL, CLIP_PRETRAINED
    except Exception:
        CLIP_MODEL, CLIP_PRETRAINED = "ViT-L-14", "laion2b_s32b_b82k"

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(
        CLIP_MODEL, pretrained=CLIP_PRETRAINED
    )
    model = model.to(device).eval()
    for p in model.parameters():
        p.requires_grad_(False)

    @torch.no_grad()
    def embed(path: Path) -> torch.Tensor:
        img = Image.open(path).convert("RGB")
        t = preprocess(img).unsqueeze(0).to(device)
        feat = model.encode_image(t)
        feat = feat / feat.norm(dim=-1, keepdim=True)
        return feat.squeeze(0).float()

    rng = random.Random(42)

    def split(xs: list[Path]):
        xs = list(xs)
        rng.shuffle(xs)
        if len(xs) <= 1:
            return xs, []
        n_val = max(1, int(round(len(xs) * 0.2)))
        n_val = min(n_val, len(xs) - 1)
        return xs[n_val:], xs[:n_val]

    ktr, kva = split(keep_paths)
    ptr, pva = split(pass_paths)
    train_items = [(p, 1.0) for p in ktr] + [(p, 0.0) for p in ptr]
    val_items = [(p, 1.0) for p in kva] + [(p, 0.0) for p in pva]
    rng.shuffle(train_items)
    rng.shuffle(val_items)
    if not val_items:
        val_items = train_items[:2]

    train_x = torch.stack([embed(p) for p, _ in train_items])
    train_y = torch.tensor([y for _, y in train_items], dtype=torch.float32, device=device)
    val_x = torch.stack([embed(p) for p, _ in val_items])
    val_y = torch.tensor([y for _, y in val_items], dtype=torch.float32, device=device)
    train_x = train_x.to(device)
    val_x = val_x.to(device)

    dim = int(train_x.shape[-1])
    head = nn.Linear(dim, 1).to(device)
    n_pos = float((train_y >= 0.5).sum().item())
    n_neg = float(len(train_y) - n_pos)
    pos_weight = torch.tensor([n_neg / max(n_pos, 1.0)], device=device)
    opt = torch.optim.Adam(head.parameters(), lr=lr)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    best_state = None
    best_metric = -1.0
    best_acc = 0.0
    stale = 0
    for epoch in range(1, int(epochs) + 1):
        head.train()
        opt.zero_grad()
        loss = loss_fn(head(train_x).squeeze(-1), train_y)
        loss.backward()
        opt.step()
        head.eval()
        with torch.no_grad():
            v_prob = torch.sigmoid(head(val_x).squeeze(-1))
            acc = float(((v_prob >= 0.5).float() == val_y).float().mean().item())
        if acc > best_metric + 1e-4:
            best_metric = acc
            best_acc = acc
            best_state = {k: v.detach().cpu().clone() for k, v in head.state_dict().items()}
            stale = 0
        else:
            stale += 1
        if stale >= 12:
            break

    if best_state is None:
        best_state = {k: v.detach().cpu().clone() for k, v in head.state_dict().items()}

    payload = {
        "state_dict": best_state,
        "dim": dim,
        "clip_model": CLIP_MODEL,
        "clip_pretrained": CLIP_PRETRAINED,
        "blend": 0.5,
        "trained_at": time.time(),
        "n_keep": len(keep_paths),
        "n_pass": len(pass_paths),
        "val_acc": best_acc,
        "val_auc": best_metric,
        "device": device,
        "epochs_ran": epoch,
    }
    import io

    buf = io.BytesIO()
    torch.save(payload, buf)
    raw = buf.getvalue()
    dest = Path(__file__).resolve().parent / "clip_ft" / "probe.pt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return {
        "ok": True,
        "probe_b64": base64.b64encode(raw).decode("ascii"),
        "bytes": len(raw),
        "n_keep": len(keep_paths),
        "n_pass": len(pass_paths),
        "val_acc": best_acc,
        "device": device,
        "epochs_ran": epoch,
        "path": str(dest),
    }
