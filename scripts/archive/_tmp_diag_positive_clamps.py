"""Diagnose which clamp kills known Keep positives."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import load_env
from db import db, init_db
from shtetl_core.cues import (
    DEFAULT_SCORE_THRESHOLD,
    MAX_NEG_TO_POS_RATIO,
    MIN_BODY_SCORE,
    MIN_HEADCOVER_SCORE,
    MIN_MALE_SCORE,
    MIN_POS_SCORE,
    NEG_SCORE_WEIGHT,
    POSITIVE_PROMPTS,
    TOP_K_CUES,
    TOP_K_NEGS,
)
from shtetl_core.scoring import CueScorer
from still_store import candidate_still_path
import torch


def main() -> None:
    load_env()
    init_db()
    with db() as conn:
        ids = [
            int(r["id"])
            for r in conn.execute(
                "SELECT id FROM candidates WHERE decision='accept' ORDER BY id"
            ).fetchall()
        ]
    scorer = CueScorer()
    thr = float(DEFAULT_SCORE_THRESHOLD)
    from PIL import Image

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
            male_sims = (img_feat @ scorer.male_feat.T).squeeze(0)
            female_sims = (img_feat @ scorer.female_feat.T).squeeze(0)
            body_sims = (img_feat @ scorer.body_feat.T).squeeze(0)
            face_sims = (img_feat @ scorer.face_feat.T).squeeze(0)
        k_pos = min(max(1, TOP_K_CUES), pos_sims.numel())
        top_pos, top_idx = torch.topk(pos_sims, k_pos)
        pos_score = float(top_pos.mean().item())
        k_neg = min(max(1, TOP_K_NEGS), neg_sims.numel())
        neg_score = float(torch.topk(neg_sims, k_neg).values.mean().item())
        head = float(head_sims.max().item())
        male = float(male_sims.max().item())
        female = float(female_sims.max().item())
        body = float(body_sims.max().item())
        face = float(face_sims.max().item())
        prompt = pos_score - float(NEG_SCORE_WEIGHT) * neg_score
        score = prompt
        if scorer.probe is not None:
            logit = scorer.probe(img_feat.float()).squeeze()
            probe_prob = float(torch.sigmoid(logit).item())
            probe_signed = 2.0 * probe_prob - 1.0
            b = float(scorer.probe_blend)
            score = (1.0 - b) * prompt + b * probe_signed
        reasons = []
        if pos_score < MIN_POS_SCORE:
            reasons.append(f"weak_pos={pos_score:.3f}<{MIN_POS_SCORE}")
        if head < MIN_HEADCOVER_SCORE:
            reasons.append(f"head={head:.3f}<{MIN_HEADCOVER_SCORE}")
        if male < MIN_MALE_SCORE or male <= female:
            reasons.append(f"male={male:.3f}/f={female:.3f}")
        if body < MIN_BODY_SCORE or body <= face:
            reasons.append(f"body={body:.3f}/face={face:.3f}")
        if pos_score > 1e-6 and (neg_score / pos_score) > MAX_NEG_TO_POS_RATIO:
            reasons.append(f"neg_ratio={neg_score/pos_score:.3f}>{MAX_NEG_TO_POS_RATIO}")
        if neg_score >= pos_score:
            reasons.append(f"neg>pos {neg_score:.3f}>={pos_score:.3f}")
        final, _, _, cue = scorer.score_image(pil)
        ok = "PASS" if final >= thr else "MISS"
        print(
            f"#{cid} {ok} final={final:.3f} raw={score:.3f} pos={pos_score:.3f} "
            f"neg={neg_score:.3f} head={head:.3f} | {', '.join(reasons) or 'no_clamp'} | {cue[:40]}"
        )


if __name__ == "__main__":
    main()
