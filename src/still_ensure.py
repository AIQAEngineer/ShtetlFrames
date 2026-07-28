"""Ensure every Review candidate has a durable local still (cand_{id}.jpg).

Call sites:
- insert_candidates (sync save + enqueue fallback)
- list_candidates (fast URL hydrate + enqueue video extract)
- serve startup backfill
- scripts/backfill_candidate_stills.py / POST /api/stills/backfill
"""

from __future__ import annotations

import queue
import subprocess
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from config import CONTACT_DIR, VIDEOS_DIR
from still_store import candidate_still_path, local_still_url, save_candidate_still

_ensure_q: queue.Queue[dict[str, Any]] = queue.Queue()
_ensure_seen: set[int] = set()
_ensure_lock = threading.Lock()
_worker_started = False
_backfill_lock = threading.Lock()
_backfill_active = False


def extract_frame(video: Path, time_sec: float, out: Path) -> bool:
    """Grab one JPEG frame at time_sec (ffmpeg, OpenCV fallback)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    t = max(0.0, float(time_sec))
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{t:.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        r = None
    if r is not None and r.returncode == 0 and out.is_file() and out.stat().st_size > 200:
        return True
    try:
        import cv2

        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            return False
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return False
        return bool(cv2.imwrite(str(out), frame)) and out.is_file() and out.stat().st_size > 200
    except Exception:
        return False


def extract_frame_from_url(
    media_url: str,
    time_sec: float,
    out: Path,
    *,
    referer: str | None = None,
    timeout_sec: float = 90.0,
) -> bool:
    """Grab one JPEG from an HLS/HTTP media URL without downloading the full file."""
    src = (media_url or "").strip()
    if not src:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    t = max(0.0, float(time_sec))
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-rw_timeout",
        "30000000",
    ]
    if referer:
        # ffmpeg headers need CRLF between fields.
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        cmd.extend(["-headers", f"Referer: {referer}\r\nUser-Agent: {ua}\r\n"])
    cmd.extend(
        [
            "-ss",
            f"{t:.3f}",
            "-i",
            src,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out),
        ]
    )
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=max(15.0, float(timeout_sec)))
        if r.returncode == 0 and out.is_file() and out.stat().st_size > 200:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # OpenCV fallback (common on Windows when ffmpeg isn't on PATH).
    try:
        import cv2

        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            return False
        try:
            if t > 0:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok or frame is None:
            return False
        return bool(cv2.imwrite(str(out), frame)) and out.is_file() and out.stat().st_size > 200
    except Exception:
        return False


def _pathe_hls_frame(source_url: str, time_sec: float, out: Path) -> bool:
    """Resolve British Pathé asset → seek one frame from HLS (fast still backfill)."""
    if "britishpathe.com" not in (source_url or "").lower():
        return False
    try:
        from britishpathe import prepare_pathe_job
    except Exception:
        return False
    try:
        job = prepare_pathe_job(source_url, "")
    except Exception as e:
        print(f"[still-ensure] pathe resolve fail: {e}"[:160], flush=True)
        return False
    if not job:
        return False
    m3u8 = (job.get("m3u8_url") or job.get("download_url") or "").strip()
    if not m3u8:
        return False
    return extract_frame_from_url(
        m3u8,
        time_sec,
        out,
        referer=(job.get("referer") or job.get("asset_url") or source_url),
    )


def _download_source(url: str, video_id: str) -> Path | None:
    from download import download_britishpathe, download_entry
    from serve import find_video_file

    existing = find_video_file(video_id)
    if existing and existing.is_file():
        return existing
    if "britishpathe.com" in (url or "").lower():
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        path = download_britishpathe(url, VIDEOS_DIR, video_id, title=video_id)
        return path if path and Path(path).is_file() else None
    result = download_entry(url, video_id, video_id=video_id)
    if result.get("error") or not result.get("path"):
        return None
    path = Path(result["path"])
    return path if path.is_file() else None


def ensure_candidate_still(
    cand_id: int,
    *,
    source_url: str = "",
    video_id: str = "",
    start_sec: float = 0.0,
    end_sec: float | None = None,
    image_url: str | None = None,
    download_video: bool = True,
) -> Path | None:
    """Return local still path, creating it from URL or source video if needed."""
    cid = int(cand_id)
    existing = candidate_still_path(cid)
    if existing.is_file() and existing.stat().st_size > 200:
        return existing

    # Optional legacy HTTP still (never Catbox — that host is disabled).
    url = (image_url or "").strip()
    if (
        url.startswith(("http://", "https://"))
        and "catbox" not in url.lower()
    ):
        saved = save_candidate_still(cid, image_url=url)
        if saved:
            return saved

    if not download_video:
        return None
    src = (source_url or "").strip()
    if not src:
        return None
    vid = (video_id or f"cand_{cid}").strip() or f"cand_{cid}"
    t0 = float(start_sec or 0.0)
    t1 = float(end_sec if end_sec is not None else t0)
    mid = t0 if t1 <= t0 else (t0 + t1) / 2.0

    # Pathé: seek one HLS frame — much faster than yt-dlp full download.
    if "britishpathe.com" in src.lower():
        with tempfile.TemporaryDirectory(prefix=f"still_{cid}_") as td:
            tmp = Path(td) / f"{cid}.jpg"
            if _pathe_hls_frame(src, mid, tmp):
                saved = save_candidate_still(cid, path=tmp)
                if saved:
                    print(f"[still-ensure] #{cid} hls-frame {saved.name}", flush=True)
                    return saved

    from serve import find_video_file

    existing = find_video_file(vid)
    owned = False
    if existing and existing.is_file():
        video = existing
    else:
        video = _download_source(src, vid)
        owned = bool(video)
    if not video:
        print(f"[still-ensure] #{cid} download failed {src[:80]}", flush=True)
        return None
    try:
        with tempfile.TemporaryDirectory(prefix=f"still_{cid}_") as td:
            tmp = Path(td) / f"{cid}.jpg"
            if not extract_frame(video, mid, tmp):
                print(f"[still-ensure] #{cid} extract failed @{mid:.2f}s", flush=True)
                return None
            saved = save_candidate_still(cid, path=tmp)
            if saved:
                print(f"[still-ensure] #{cid} saved {saved.name}", flush=True)
            return saved
    finally:
        if owned and video and Path(video).is_file():
            try:
                Path(video).unlink(missing_ok=True)
            except OSError:
                pass


def start_ensure_worker() -> None:
    """Idempotent: start the background still-ensure daemon (serve process)."""
    global _worker_started
    with _ensure_lock:
        if _worker_started:
            return
        _worker_started = True
        threading.Thread(
            target=_ensure_worker, daemon=True, name="still-ensure"
        ).start()


def enqueue_ensure_still(row: dict[str, Any]) -> None:
    """Queue a background video-frame extract for a missing still."""
    try:
        cid = int(row["id"])
    except (KeyError, TypeError, ValueError):
        return
    if local_still_url(cid):
        return
    if not (row.get("source_url") or "").strip():
        return
    start_ensure_worker()
    with _ensure_lock:
        if cid in _ensure_seen:
            return
        _ensure_seen.add(cid)
    _ensure_q.put(
        {
            "id": cid,
            "source_url": (row.get("source_url") or "").strip(),
            "video_id": (row.get("video_id") or "").strip(),
            "start_sec": row.get("start_sec") or 0,
            "end_sec": row.get("end_sec"),
            "image_url": row.get("image_url"),
        }
    )


def _ensure_worker() -> None:
    while True:
        row = _ensure_q.get()
        try:
            cid = int(row["id"])
            if local_still_url(cid):
                continue
            ensure_candidate_still(
                cid,
                source_url=str(row.get("source_url") or ""),
                video_id=str(row.get("video_id") or ""),
                start_sec=float(row.get("start_sec") or 0),
                end_sec=row.get("end_sec"),
                image_url=row.get("image_url"),
                download_video=True,
            )
        except Exception as e:
            print(f"[still-ensure] worker error: {e}"[:200], flush=True)
        finally:
            with _ensure_lock:
                try:
                    _ensure_seen.discard(int(row.get("id") or 0))
                except Exception:
                    pass
            time.sleep(0.15)


def missing_still_rows(*, limit: int = 5000) -> list[dict[str, Any]]:
    from db import db, init_db

    init_db()
    CONTACT_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, video_id, start_sec, end_sec, source_url, image_url, notes
            FROM candidates
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if local_still_url(int(d["id"])):
            continue
        if not (d.get("source_url") or "").strip():
            continue
        out.append(d)
    return out


def missing_still_ids(*, limit: int = 5000) -> list[int]:
    return [int(r["id"]) for r in missing_still_rows(limit=limit)]


def backfill_missing_stills(
    *,
    limit: int = 5000,
    on_status: Any | None = None,
) -> dict[str, Any]:
    """Download each source once and extract frames for every missing still.

    Groups by (video_id, source_url) so Pathé assets are not re-downloaded
    per candidate. Safe to call from the serve process (background thread).
    Pathé prefers HLS single-frame seeks (no full yt-dlp download).
    """
    rows = missing_still_rows(limit=limit)
    if not rows:
        return {"ok": True, "missing": 0, "saved": 0, "failed": 0}

    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        vid = (r.get("video_id") or "unknown").strip() or "unknown"
        url = (r.get("source_url") or "").strip()
        by_key[(vid, url)].append(r)

    if on_status:
        on_status(f"Backfilling {len(rows)} still(s) across {len(by_key)} video(s)…")
    else:
        print(
            f"[still-backfill] {len(rows)} still(s) across {len(by_key)} video(s)…",
            flush=True,
        )

    ok_n = 0
    fail_n = 0
    for (vid, url), group in by_key.items():
        is_pathe = "britishpathe.com" in url.lower()
        # Fast path: Pathé HLS seek one frame per candidate (no full download).
        if is_pathe:
            m3u8 = ""
            referer = url
            try:
                from britishpathe import prepare_pathe_job

                job = prepare_pathe_job(url, vid)
                if job:
                    m3u8 = (job.get("m3u8_url") or job.get("download_url") or "").strip()
                    referer = (job.get("referer") or job.get("asset_url") or url)
            except Exception as e:
                print(f"[still-backfill] pathe resolve fail {vid}: {e}"[:160], flush=True)
            if m3u8:
                with tempfile.TemporaryDirectory(prefix="shtetl_backfill_") as tmp:
                    tmpdir = Path(tmp)
                    # Reuse one OpenCV capture across timestamps on the same Pathé reel.
                    cap = None
                    try:
                        try:
                            import cv2

                            cap = cv2.VideoCapture(m3u8)
                            if not cap.isOpened():
                                cap.release()
                                cap = None
                        except Exception:
                            cap = None
                        for r in group:
                            cid = int(r["id"])
                            if local_still_url(cid):
                                ok_n += 1
                                continue
                            t0 = float(r.get("start_sec") or 0.0)
                            t1 = float(r.get("end_sec") or t0)
                            t = t0 if t1 <= t0 else (t0 + t1) / 2.0
                            tmp_jpg = tmpdir / f"{cid}.jpg"
                            got = False
                            if cap is not None:
                                try:
                                    if t > 0:
                                        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                                    ok_f, frame = cap.read()
                                    if ok_f and frame is not None:
                                        got = bool(cv2.imwrite(str(tmp_jpg), frame)) and (
                                            tmp_jpg.is_file() and tmp_jpg.stat().st_size > 200
                                        )
                                except Exception:
                                    got = False
                            if not got:
                                got = extract_frame_from_url(
                                    m3u8, t, tmp_jpg, referer=referer
                                )
                            if not got:
                                fail_n += 1
                                print(f"[still-backfill] #{cid} hls-frame fail", flush=True)
                                continue
                            if save_candidate_still(cid, path=tmp_jpg):
                                ok_n += 1
                                print(f"[still-backfill] #{cid} hls-frame ok", flush=True)
                            else:
                                fail_n += 1
                    finally:
                        if cap is not None:
                            try:
                                cap.release()
                            except Exception:
                                pass
                continue

        path = _download_source(url, vid)
        if not path:
            fail_n += len(group)
            print(f"[still-backfill] download fail {vid}", flush=True)
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="shtetl_backfill_") as tmp:
                tmpdir = Path(tmp)
                for r in group:
                    cid = int(r["id"])
                    if local_still_url(cid):
                        ok_n += 1
                        continue
                    t0 = float(r.get("start_sec") or 0.0)
                    t1 = float(r.get("end_sec") or t0)
                    t = t0 if t1 <= t0 else (t0 + t1) / 2.0
                    tmp_jpg = tmpdir / f"{cid}.jpg"
                    if not extract_frame(path, t, tmp_jpg):
                        fail_n += 1
                        print(f"[still-backfill] #{cid} extract fail", flush=True)
                        continue
                    if save_candidate_still(cid, path=tmp_jpg):
                        ok_n += 1
                    else:
                        fail_n += 1
        finally:
            try:
                for p in VIDEOS_DIR.glob(f"{vid}*"):
                    if p.is_file() and p.suffix.lower() in {
                        ".mp4",
                        ".webm",
                        ".mkv",
                        ".avi",
                        ".mov",
                        ".part",
                    }:
                        p.unlink(missing_ok=True)
            except OSError:
                pass

    left = len(missing_still_rows(limit=limit))
    print(f"[still-backfill] done saved={ok_n} failed={fail_n} left={left}", flush=True)
    return {
        "ok": True,
        "missing": len(rows),
        "saved": ok_n,
        "failed": fail_n,
        "still_missing": left,
    }


def backfill_running() -> bool:
    with _backfill_lock:
        return bool(_backfill_active)


def stills_status(*, limit: int = 5000) -> dict[str, Any]:
    """Missing still count + whether a background backfill is active."""
    missing = missing_still_ids(limit=limit)
    return {
        "ok": True,
        "missing": len(missing),
        "running": backfill_running(),
        "sample_ids": missing[:12],
    }


def kick_backfill_missing_stills(*, limit: int = 5000) -> bool:
    """Start at most one background backfill pass. Returns True if started."""
    global _backfill_active
    with _backfill_lock:
        if _backfill_active:
            return False
        _backfill_active = True

    def _run() -> None:
        global _backfill_active
        try:
            backfill_missing_stills(limit=limit)
        except Exception as e:
            print(f"[still-backfill] failed: {e}"[:200], flush=True)
        finally:
            with _backfill_lock:
                _backfill_active = False

    threading.Thread(target=_run, daemon=True, name="still-backfill").start()
    return True
