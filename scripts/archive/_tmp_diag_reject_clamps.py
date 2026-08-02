"""Diagnose Pass (reject) clamp/raw scores."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch
from PIL import Image

from config import load_env
from db import db, init_db
from shtetl_core.cues import (
    DEFAULT_SCORE_THRESHOLD,
    NEG_SCORE_WEIGHT,
    TOP_K_CUES,
    TOP_K_NEGS,
)
from shtetl_core.scoring import CueScorer
from still_store import candidate_still_path


def main() -> None:
    load_env()
    init_db()
    scorer = CueScorer()
    thr = float(DEFAULT_SCORE_THRESHOLD)
    with db() as conn:
        ids = [
            int(r["id"])
            for r in conn.execute(
                "SELECT id FROM candidates WHERE decision='reject' ORDER BY id"
            ).fetchall()
        ]
    for cid in ids:
        path = candidate_still_path(cid)
        if not path.is_file():
            print(f"#{cid} no_still")
            continue
        pil = Image.open(path).convert("RGB")
        image = scorer.preprocess(pil).unsqueeze(0).to(scorer.device)
        with torch.no_grad():
            img_feat = scorer.model.encode_image(image)
            img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
            pos_sims = (img_feat @ scorer.pos_feat.T).squeeze(0)
            neg_sims = (img_feat @ scorer.neg_feat.T).squeeze(0)
            head_sims = (img_feat @ scorer.head_feat.T).squeeze(0)
        k_pos = min(max(1, TOP_K_CUES), pos_sims.numel())
        pos_score = float(torch.topk(pos_sims, k_pos).values.mean().item())
        k_neg = min(max(1, TOP_K_NEGS), neg_sims.numel())
        neg_score = float(torch.topk(neg_sims, k_neg).values.mean().item())
        head = float(head_sims.max().item())
        prompt = pos_score - float(NEG_SCORE_WEIGHT) * neg_score
        score = prompt
        if scorer.probe is not None:
            logit = scorer.probe(img_feat.float()).squeeze()
            probe_prob = float(torch.sigmoid(logit).item())
            probe_signed = 2.0 * probe_prob - 1.0
            b = float(scorer.probe_blend)
            score = (1.0 - b) * prompt + b * probe_signed
        final, _, _, _ = scorer.score_image(pil)
        ratio = (neg_score / pos_score) if pos_score > 1e-6 else 999.0
        print(
            f"#{cid} final={final:.3f} raw={score:.3f} pos={pos_score:.3f} "
            f"neg={neg_score:.3f} ratio={ratio:.3f} head={head:.3f} "
            f"pass={final >= thr}"
        )


if __name__ == "__main__":
    main()
