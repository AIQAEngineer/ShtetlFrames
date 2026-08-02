"""Extract distinct on-screen text from a video via scene keyframes + OpenAI vision OCR."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://api.openai.com/v1/chat/completions"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def ahash(gray: np.ndarray, size: int = 16) -> np.ndarray:
    small = cv2.resize(gray, (size, size))
    return (small > small.mean()).astype(np.uint8).flatten()


def ham(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.sum(a != b))


def scene_keyframes(video: Path, sample_fps: float = 2.0, change_thr: float = 18.0):
    """Return list of (time_sec, frame_bgr) at scene changes + forced early samples."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps / sample_fps)))
    prev_small = None
    frames = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step != 0:
            idx += 1
            continue
        t = idx / fps
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (64, 48)).astype(np.float32)
        if prev_small is None:
            change = 999.0
        else:
            change = float(np.mean(np.abs(small - prev_small)))
        prev_small = small
        # Keep strong scene cuts; also dense sample first 20s (titles/intertitles)
        if change >= change_thr or t <= 20.0:
            frames.append((t, frame.copy(), change))
        idx += 1
    cap.release()
    return frames


def looks_like_intertitle(gray: np.ndarray) -> bool:
    """Strict heuristic for title cards / intertitles (not dark photographic scenes)."""
    h, w = gray.shape
    g = gray.copy()
    g[int(h * 0.82) :, int(w * 0.72) :] = int(np.median(g))
    bright = g > 145
    dark = g < 55
    bf = float(bright.mean())
    df = float(dark.mean())
    if bf < 0.004 or bf > 0.22:
        return False
    bg = g[~bright]
    if bg.size < 100:
        return False
    bg_std = float(bg.std())
    row = bright.mean(axis=1)
    peaks = 0
    in_peak = False
    for v in row:
        if v > 0.015 and not in_peak:
            peaks += 1
            in_peak = True
        elif v <= 0.015:
            in_peak = False
    if peaks < 1:
        return False
    # Classic plain intertitle: very dark + low texture
    if df > 0.82 and bg_std < 22 and 0.004 <= bf <= 0.12:
        return True
    # Bordered title card: dark center + decorative bright border/text
    center = g[int(h * 0.12) : int(h * 0.88), int(w * 0.08) : int(w * 0.92)]
    center_dark = float((center < 60).mean())
    border = np.concatenate(
        [g[:6, :].ravel(), g[-6:, :].ravel(), g[:, :6].ravel(), g[:, -6:].ravel()]
    )
    border_bright = float((border > 145).mean())
    if center_dark > 0.55 and border_bright > 0.12 and peaks >= 2 and bg_std < 35:
        return True
    return False


def cluster_frames(items, max_ham: int = 10):
    """items: list of (t, frame, meta...). Return cluster reps with time ranges."""
    clusters = []  # [rep_idx, [member_idx...]]
    hashes = []
    for i, (t, frame, *_) in enumerate(items):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        ah = ahash(gray)
        hashes.append(ah)
        placed = False
        for c in clusters:
            if ham(ah, hashes[c[0]]) <= max_ham:
                c[1].append(i)
                placed = True
                break
        if not placed:
            clusters.append([i, [i]])
    out = []
    for ci, (ri, members) in enumerate(clusters):
        # prefer mid-duration / higher contrast representative
        def score(i):
            g = cv2.cvtColor(items[i][1], cv2.COLOR_BGR2GRAY)
            return float(g.std())

        best = max(members, key=score)
        times = [items[m][0] for m in members]
        out.append(
            {
                "cluster": ci,
                "t": round(items[best][0], 2),
                "t_start": round(min(times), 2),
                "t_end": round(max(times), 2),
                "n": len(members),
                "frame": items[best][1],
            }
        )
    return out


def encode_jpg(frame_bgr: np.ndarray, scale: float = 3.0, quality: int = 92) -> str:
    if scale != 1.0:
        frame_bgr = cv2.resize(
            frame_bgr,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


SYSTEM = (
    "You OCR archival film frames. Extract ALL readable on-screen text "
    "(intertitles, captions, signs, inscriptions), preserving original language "
    "and diacritics (Czech, Latin, Hebrew, Yiddish, German, etc.). "
    "Ignore the modern 'nfa' / NFA archive watermark logo in the corner. "
    "If text is partially illegible, transcribe best-effort and mark uncertain "
    "parts with [?]. If there is no meaningful text besides the watermark, "
    "return an empty texts array. JSON only."
)


def ocr_frame(b64_jpg: str, model: str, api_key: str, timeout: float = 60.0) -> dict:
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "frame_ocr",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "has_text": {"type": "boolean"},
                        "kind": {
                            "type": "string",
                            "enum": [
                                "intertitle",
                                "caption",
                                "sign",
                                "inscription",
                                "mixed",
                                "none",
                            ],
                        },
                        "texts": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "language_guess": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": [
                        "has_text",
                        "kind",
                        "texts",
                        "language_guess",
                        "notes",
                    ],
                },
            },
        },
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract distinct readable text from this film frame.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_jpg}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
    }
    r = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def norm_text(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s\-áčďéěíňóřšťúůýžäöüßא-תʔ׳״\[\]\.\(\)]", "", s, flags=re.I)
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sample-fps", type=float, default=2.0)
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini").strip() or "gpt-5.4-mini"
    if not api_key:
        raise SystemExit("OPENAI_API_KEY not set")

    out_dir = args.out or (ROOT / "output" / f"{args.video.stem}_ocr")
    frames_dir = out_dir / "ocr_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    def _p(msg: str) -> None:
        # Windows consoles are often cp1252; keep progress printable.
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)

    _p(f"Sampling keyframes from {args.video.name} ...")
    keyed = scene_keyframes(args.video, sample_fps=args.sample_fps)
    _p(f"  scene/early samples: {len(keyed)}")

    # Strict intertitle scan at sample_fps across full video
    cap = cv2.VideoCapture(str(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps / args.sample_fps)))
    inter = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if looks_like_intertitle(gray):
                inter.append((idx / fps, frame.copy(), 0.0))
        idx += 1
    cap.release()
    _p(f"  intertitle-like samples: {len(inter)}")

    # OCR pool:
    # 1) all strict intertitles
    # 2) early film scene samples (titles/captions often cluster at start)
    # 3) a limited set of later scene cuts (signs/inscriptions)
    early = [x for x in keyed if x[0] <= 30.0]
    later_cuts = [x for x in keyed if x[0] > 30.0 and x[2] >= 28.0]
    combined = inter + early + later_cuts
    # High ham tolerance: archival grain/flicker shifts aHash a lot on same card
    clusters = cluster_frames(combined, max_ham=22)
    _p(f"  unique clusters: {len(clusters)}")

    selected = []
    later_kept = 0
    for c in sorted(clusters, key=lambda x: x["t"]):
        g = cv2.cvtColor(c["frame"], cv2.COLOR_BGR2GRAY)
        it = looks_like_intertitle(g)
        if it or c["t"] <= 30.0:
            selected.append(c)
        elif later_kept < 25:
            if float((g < 80).mean()) > 0.35 or float(g.std()) > 45:
                selected.append(c)
                later_kept += 1
    # Hard cap: prefer intertitles and earliest times
    if len(selected) > 55:
        selected.sort(
            key=lambda c: (
                0 if looks_like_intertitle(cv2.cvtColor(c["frame"], cv2.COLOR_BGR2GRAY)) else 1,
                c["t"],
            )
        )
        selected = selected[:55]
    selected.sort(key=lambda c: c["t"])
    _p(f"  OCR targets: {len(selected)}")

    jobs = []
    for c in selected:
        path = frames_dir / f"t{c['t']:07.2f}s_c{c['cluster']:03d}.jpg"
        cv2.imwrite(str(path), c["frame"])
        c["path"] = str(path)
        jobs.append(c)

    results = []
    errors = 0

    def work(c):
        b64 = encode_jpg(c["frame"], scale=3.0)
        data = ocr_frame(b64, model=model, api_key=api_key)
        return c, data

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, c) for c in jobs]
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                c, data = fut.result()
            except Exception as e:
                errors += 1
                print(f"  [{done}/{len(jobs)}] ERROR: {e}".encode("ascii", "replace").decode("ascii"))
                continue
            texts = [t.strip() for t in (data.get("texts") or []) if t and t.strip()]
            # drop watermark-only leftovers
            texts = [t for t in texts if norm_text(t) not in {"nfa", "nf a", "nfa logo"}]
            has = bool(data.get("has_text")) and bool(texts)
            row = {
                "t": c["t"],
                "t_start": c["t_start"],
                "t_end": c["t_end"],
                "cluster": c["cluster"],
                "path": c["path"],
                "has_text": has,
                "kind": data.get("kind"),
                "texts": texts,
                "joined": "\n".join(texts),
                "language_guess": data.get("language_guess"),
                "notes": data.get("notes"),
            }
            results.append(row)
            preview = row["joined"].replace("\n", " | ")[:120] if has else "(no text)"
            _p(f"  [{done}/{len(jobs)}] t={c['t']:.1f}s {row['kind']}: {preview}")

    results.sort(key=lambda r: r["t"])

    # Deduplicate distinct text blocks
    distinct = []
    seen = []
    for r in results:
        if not r["has_text"]:
            continue
        key = norm_text(r["joined"])
        if not key or len(key) < 2:
            continue
        dup = False
        for s in seen:
            # near-duplicate if one contains the other or high overlap
            if key == s or key in s or s in key:
                dup = True
                break
            # token Jaccard
            a, b = set(key.split()), set(s.split())
            if a and b and len(a & b) / len(a | b) >= 0.85:
                dup = True
                break
        if dup:
            continue
        seen.append(key)
        distinct.append(r)

    report = {
        "video": str(args.video),
        "model": model,
        "clusters_ocrd": len(results),
        "errors": errors,
        "distinct_text_count": len(distinct),
        "distinct": [
            {
                "t": d["t"],
                "t_start": d["t_start"],
                "t_end": d["t_end"],
                "kind": d["kind"],
                "language_guess": d["language_guess"],
                "texts": d["texts"],
                "joined": d["joined"],
                "path": d["path"],
                "notes": d["notes"],
            }
            for d in distinct
        ],
        "all_with_text": [r for r in results if r["has_text"]],
    }

    json_path = out_dir / "distinct_text.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        f"# Distinct text from `{args.video.name}`",
        "",
        f"- Duration sampled; OCR model: `{model}`",
        f"- Distinct text blocks: **{len(distinct)}**",
        "",
    ]
    for i, d in enumerate(distinct, 1):
        md_lines.append(f"## {i}. t={d['t_start']:.1f}–{d['t_end']:.1f}s ({d['kind']})")
        md_lines.append("")
        md_lines.append("```")
        md_lines.append(d["joined"])
        md_lines.append("```")
        if d.get("language_guess"):
            md_lines.append("")
            md_lines.append(f"_Language guess: {d['language_guess']}_")
        md_lines.append("")

    md_path = out_dir / "distinct_text.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    _p(f"\nWrote {json_path}")
    _p(f"Wrote {md_path}")
    _p(f"Distinct text blocks: {len(distinct)}")


if __name__ == "__main__":
    main()
