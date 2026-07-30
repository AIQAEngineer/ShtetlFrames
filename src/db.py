"""SQLite persistence for ShtetlFrames queue, jobs, and review candidates."""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from config import DB_PATH, OUTPUT_DIR

# Serialize writers — many scrape threads opening connections was freezing on Windows.
_DB_WRITE_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS queue_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  title TEXT,
  year TEXT DEFAULT '',
  source TEXT DEFAULT '',
  downloadable TEXT DEFAULT 'yes',
  status TEXT DEFAULT 'pending',
  hub_url TEXT DEFAULT '',
  error TEXT DEFAULT '',
  detail TEXT DEFAULT '',
  created_at REAL
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  status TEXT DEFAULT 'idle',
  phase TEXT DEFAULT 'idle',
  message TEXT DEFAULT '',
  progress REAL DEFAULT 0,
  discovered INTEGER DEFAULT 0,
  total INTEGER DEFAULT 0,
  completed INTEGER DEFAULT 0,
  hits INTEGER DEFAULT 0,
  max_videos TEXT DEFAULT 'all',
  workers INTEGER DEFAULT 2,
  hub_url TEXT DEFAULT '',
  error TEXT DEFAULT '',
  updated_at REAL
);

CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  start_sec REAL NOT NULL,
  end_sec REAL NOT NULL,
  peak_score REAL,
  mean_score REAL,
  rank_score REAL,
  hit_count INTEGER,
  best_cue TEXT,
  source_url TEXT,
  image_url TEXT,
  decision TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  label TEXT DEFAULT 'orthodox_dress_candidate_not_identity',
  created_at REAL
);

CREATE INDEX IF NOT EXISTS idx_cand_rank ON candidates(rank_score DESC);
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue_items(status);

CREATE TABLE IF NOT EXISTS train_clips (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asset_id TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  title TEXT DEFAULT '',
  year TEXT DEFAULT '',
  query TEXT NOT NULL DEFAULT 'rabbi',
  thumb_url TEXT DEFAULT '',
  decision TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  created_at REAL,
  labeled_at REAL
);
CREATE INDEX IF NOT EXISTS idx_train_query_decision ON train_clips(query, decision);
"""


def _connect() -> sqlite3.Connection:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


@contextmanager
def db(*, write: bool = False) -> Iterator[sqlite3.Connection]:
    """Open SQLite. Pass write=True for mutations so writers serialize without blocking reads."""
    acquired = False
    if write:
        _DB_WRITE_LOCK.acquire()
        acquired = True
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        if acquired:
            _DB_WRITE_LOCK.release()


def init_db() -> None:
    with db(write=True) as conn:
        conn.executescript(SCHEMA)
        # Migrations for older DBs
        cols = {r[1] for r in conn.execute("PRAGMA table_info(queue_items)").fetchall()}
        if "error" not in cols:
            conn.execute("ALTER TABLE queue_items ADD COLUMN error TEXT DEFAULT ''")
        if "detail" not in cols:
            conn.execute("ALTER TABLE queue_items ADD COLUMN detail TEXT DEFAULT ''")
        for jid in (
            "discover",
            "scrape",
            "pathe_discover",
            "pathe_scrape",
            "train_seed",
            "clip_ft",
        ):
            conn.execute(
                "INSERT OR IGNORE INTO jobs (id, status, phase, updated_at) VALUES (?, 'idle', 'idle', ?)",
                (jid, time.time()),
            )
        # Older DBs created before train_clips existed.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS train_clips (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              asset_id TEXT NOT NULL,
              url TEXT NOT NULL UNIQUE,
              title TEXT DEFAULT '',
              year TEXT DEFAULT '',
              query TEXT NOT NULL DEFAULT 'rabbi',
              thumb_url TEXT DEFAULT '',
              decision TEXT DEFAULT '',
              notes TEXT DEFAULT '',
              created_at REAL,
              labeled_at REAL
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_train_query_decision "
            "ON train_clips(query, decision)"
        )


def set_job(job_id: str, **kwargs: Any) -> dict:
    kwargs["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in kwargs)
    with db(write=True) as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*kwargs.values(), job_id))
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else {}


def get_job(job_id: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else {"id": job_id, "status": "idle", "phase": "idle"}


def list_jobs() -> dict[str, dict]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM jobs").fetchall()
    return {r["id"]: dict(r) for r in rows}


_PATHE_URL_SQL = "url LIKE '%britishpathe.com%'"
_NON_PATHE_URL_SQL = "url NOT LIKE '%britishpathe.com%'"


def _source_sql(source: str) -> str:
    """Map a queue source filter to a WHERE fragment ('' = no filter)."""
    s = (source or "").strip().lower()
    if s in ("pathe", "britishpathe", "british_pathe", "british-pathe"):
        return _PATHE_URL_SQL
    if s in ("youtube", "yt", "web", "non_pathe", "non-pathe"):
        return _NON_PATHE_URL_SQL
    return ""


def clear_queue(source: str = "") -> int:
    """Delete queue rows (all, or scoped to one source). Returns rows deleted."""
    frag = _source_sql(source)
    with db(write=True) as conn:
        if frag:
            cur = conn.execute(f"DELETE FROM queue_items WHERE {frag}")
        else:
            cur = conn.execute("DELETE FROM queue_items")
        return int(cur.rowcount or 0)


def insert_queue_items(items: list[dict], hub_url: str = "") -> dict:
    """Batch-insert discovered items; skip duplicates. Returns n_added / n_skipped.

    Pathé asset URLs are normalized to a canonical form so host/slash variants
    do not create duplicate rows (UNIQUE on url + INSERT OR IGNORE).
    """
    added = 0
    skipped = 0
    now = time.time()
    rows = []
    seen_batch: set[str] = set()
    for it in items:
        url = (it.get("url") or "").strip()
        if not url:
            skipped += 1
            continue
        if "britishpathe.com" in url.lower():
            try:
                from britishpathe import normalize_asset_url

                url = normalize_asset_url(url) or url
            except Exception:
                pass
        if url in seen_batch:
            skipped += 1
            continue
        seen_batch.add(url)
        rows.append(
            (
                url,
                (it.get("title") or url)[:300],
                it.get("year") or "",
                it.get("source") or "",
                it.get("downloadable") or "yes",
                hub_url,
                now,
            )
        )
    if not rows:
        return {"n_added": 0, "n_skipped": skipped}
    with db(write=True) as conn:
        before = conn.execute("SELECT COUNT(*) AS n FROM queue_items").fetchone()["n"]
        conn.executemany(
            """INSERT OR IGNORE INTO queue_items
               (url, title, year, source, downloadable, status, hub_url, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            rows,
        )
        after = conn.execute("SELECT COUNT(*) AS n FROM queue_items").fetchone()["n"]
        added = after - before
        skipped += len(rows) - added
        # Refresh placeholder titles when we later learn a real name.
        for url, title, _year, _src, _dl, _hub, _ts in rows:
            if not title or title.lower().startswith("british pathé asset"):
                continue
            if title.lower().startswith("asset ") and title[6:].isdigit():
                continue
            conn.execute(
                """UPDATE queue_items SET title=?
                   WHERE url=? AND (
                     title LIKE 'British Pathé asset %'
                     OR title LIKE 'British Pathe asset %'
                     OR title LIKE 'Asset %'
                     OR title='' OR title IS NULL
                   )""",
                (title, url),
            )
    return {"n_added": added, "n_skipped": skipped}


def list_queue_page(
    *,
    offset: int = 0,
    limit: int = 100,
    status: str = "",
    q: str = "",
    source: str = "",
) -> dict:
    """Paginated queue for large discovers — returns items + total matching."""
    offset = max(0, int(offset))
    limit = max(1, min(int(limit), 500))
    clauses = ["1=1"]
    params: list = []
    frag = _source_sql(source)
    if frag:
        clauses.append(frag)
    if status:
        clauses.append("status=?")
        params.append(status)
    if q:
        clauses.append("(title LIKE ? OR url LIKE ? OR error LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    where = " AND ".join(clauses)
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM queue_items WHERE {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"""SELECT id, url, title, year, source, downloadable, status, error, detail, hub_url, created_at
                FROM queue_items WHERE {where}
                ORDER BY
                  CASE status
                    WHEN 'downloading' THEN 0
                    WHEN 'scanning' THEN 1
                    WHEN 'uploading' THEN 2
                    WHEN 'error' THEN 3
                    WHEN 'queued' THEN 4
                    WHEN 'pending' THEN 5
                    WHEN 'done' THEN 6
                    ELSE 7
                  END,
                  id DESC
                LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        ).fetchall()
    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def reset_stale_jobs() -> None:
    """Clear 'running' jobs left over after a server kill/crash. Call once at startup only."""
    now = time.time()
    with db(write=True) as conn:
        for jid in ("discover", "scrape", "pathe_discover", "pathe_scrape"):
            row = conn.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()
            if row and row["status"] == "running":
                conn.execute(
                    """UPDATE jobs SET status='idle', phase='idle',
                       message='Previous run interrupted — click Start again.',
                       error='', progress=0, updated_at=? WHERE id=?""",
                    (now, jid),
                )
        conn.execute(
            "UPDATE queue_items SET status='pending', detail='' WHERE status IN "
            "('queued','scanning','downloading','uploading')"
        )


def reclaim_inflight_queue() -> int:
    """Put stuck scanning/downloading/uploading rows back to pending (safe after kill)."""
    with db(write=True) as conn:
        cur = conn.execute(
            "UPDATE queue_items SET status='pending', detail='', error='' "
            "WHERE status IN ('scanning','downloading','uploading','queued')"
        )
        return int(cur.rowcount or 0)


def _queue_aggregate(frag: str = "") -> dict:
    """One aggregate pass over queue_items; both stats views format from this."""
    where = f" WHERE {frag}" if frag else ""
    with db() as conn:
        row = conn.execute(
            f"""
            SELECT
              COUNT(*) AS n_queue,
              SUM(CASE WHEN downloadable='yes' THEN 1 ELSE 0 END) AS n_downloadable,
              SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS n_pending_fresh,
              SUM(CASE WHEN status IN ('pending','queued','scanning','downloading','uploading')
                        AND downloadable='yes' THEN 1 ELSE 0 END) AS n_pending,
              SUM(CASE WHEN status IN ('scanning','downloading','uploading') THEN 1 ELSE 0 END) AS n_active,
              SUM(CASE WHEN status IN ('queued','scanning','downloading','uploading') THEN 1 ELSE 0 END) AS n_active_q,
              SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS n_done,
              SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS n_error
            FROM queue_items{where}
            """
        ).fetchone()
    return {k: int(row[k] or 0) for k in row.keys()}


def queue_stats(source: str = "") -> dict:
    agg = _queue_aggregate(_source_sql(source))
    return {
        "n_queue": agg["n_queue"],
        "n_downloadable": agg["n_downloadable"],
        "n_pending": agg["n_pending"],
        # Errors are cleared and retried when Start scrape runs again.
        "n_retryable": agg["n_error"],
        "n_done": agg["n_done"],
        "n_active": agg["n_active"],
        "n_error": agg["n_error"],
    }


def list_queue(limit: int = 500) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM queue_items ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_queue_url(url: str) -> bool:
    with db(write=True) as conn:
        cur = conn.execute("DELETE FROM queue_items WHERE url=?", (url,))
        return cur.rowcount > 0


def queue_claim_from_end() -> bool:
    """True when Settings/env QUEUE_CLAIM_ORDER=end (score newest queue rows first)."""
    import os

    raw = (os.environ.get("QUEUE_CLAIM_ORDER") or "").strip().lower()
    if not raw:
        try:
            from settings_store import get_setting

            raw = (get_setting("QUEUE_CLAIM_ORDER") or "start").strip().lower()
        except Exception:
            raw = "start"
    return raw in ("end", "desc", "newest", "lifo", "tail", "back")


def _queue_id_dir() -> str:
    """SQL id direction: ASC = front/oldest, DESC = back/newest."""
    return "DESC" if queue_claim_from_end() else "ASC"


def take_pending(
    limit: int | None,
    *,
    source: str = "youtube",
    only_pending: bool = False,
) -> list[dict]:
    """Fetch claimable downloadable rows; optionally cap. Marks them 'queued'.

    ``source='youtube'`` (default) excludes British Pathé URLs — use the dedicated
    Pathé scrape for those; ``source='pathe'`` claims Pathé rows only.
    Default mode also reclaims stuck in-flight rows and previous errors so Start
    scrape retries them; ``only_pending=True`` claims fresh ``pending`` rows only,
    so a continuous discover+scrape never double-claims in-flight work.
    Order follows Settings ``QUEUE_CLAIM_ORDER`` (start=oldest id, end=newest id).
    """
    frag = _source_sql(source)
    and_frag = f" AND {frag}" if frag else ""
    id_dir = _queue_id_dir()
    if only_pending:
        claim = f"status='pending' AND downloadable='yes'{and_frag}"
        order = f"ORDER BY id {id_dir}"
    else:
        claim = (
            "status IN ('pending','queued','scanning','downloading','uploading','error') "
            f"AND downloadable='yes'{and_frag}"
        )
        order = (
            "ORDER BY CASE status "
            "WHEN 'pending' THEN 0 "
            "WHEN 'queued' THEN 1 "
            "WHEN 'error' THEN 2 "
            f"ELSE 3 END, id {id_dir}"
        )
    with db(write=True) as conn:
        if limit is None:
            rows = conn.execute(
                f"SELECT * FROM queue_items WHERE {claim} {order}"
            ).fetchall()
        else:
            # Prefer fresh pending first, then retry errors / stuck jobs.
            rows = conn.execute(
                f"SELECT * FROM queue_items WHERE {claim} {order} LIMIT ?",
                (int(limit),),
            ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            conn.executemany(
                "UPDATE queue_items SET status='queued', error='', detail='' WHERE id=?",
                [(i,) for i in ids],
            )
    return [dict(r) for r in rows]


def take_pending_pathe(limit: int | None, *, only_pending: bool = True) -> list[dict]:
    """Claim British Pathé rows for scrape. Default: only fresh ``pending``.

    Use ``only_pending=False`` to also reclaim stuck in-flight / error rows
    (manual cold start). Continuous discover+scrape must keep ``only_pending=True``
    so in-flight work is never double-claimed.
    """
    return take_pending(limit, source="pathe", only_pending=only_pending)


def requeue_pathe_errors() -> int:
    """Reset Pathé error rows to pending so a new scrape can retry them."""
    with db(write=True) as conn:
        cur = conn.execute(
            f"UPDATE queue_items SET status='pending', error='', detail='' "
            f"WHERE status='error' AND {_PATHE_URL_SQL}"
        )
        return int(cur.rowcount or 0)


def requeue_pathe_stuck() -> int:
    """Reset Pathé in-flight rows to pending (dead pod / crashed scrape).

    Does not touch ``error`` — those may be definitive (still-image, gone playlist).
    Use ``requeue_pathe_errors`` when intentionally retrying failures.
    """
    with db(write=True) as conn:
        cur = conn.execute(
            f"UPDATE queue_items SET status='pending', error='', detail='' "
            f"WHERE {_PATHE_URL_SQL} AND status IN "
            f"('queued','scanning','downloading','uploading')"
        )
        return int(cur.rowcount or 0)


def reclaim_orphan_pathe_scanning(active_ids: set[int] | list[int]) -> int:
    """Requeue Pathé ``scanning`` rows that no live worker owns.

    The claim loop is the source of truth via ``active_ids``. Rows left in
    ``scanning`` after a worker death otherwise block the UI forever.
    """
    keep = {int(x) for x in (active_ids or []) if x is not None}
    with db(write=True) as conn:
        rows = conn.execute(
            f"SELECT id FROM queue_items WHERE status='scanning' AND {_PATHE_URL_SQL}"
        ).fetchall()
        orphan = [int(r["id"]) for r in rows if int(r["id"]) not in keep]
        if not orphan:
            return 0
        conn.executemany(
            "UPDATE queue_items SET status='pending', error='', "
            "detail='reclaim_orphan_scanning' WHERE id=?",
            [(i,) for i in orphan],
        )
        return len(orphan)


def clear_queue_pathe() -> int:
    """Delete only British Pathé rows from the queue. Returns rows deleted."""
    n = clear_queue(source="pathe")
    try:
        from britishpathe import clear_discover_cursor

        clear_discover_cursor()
    except Exception:
        pass
    return n


def list_youtube_pathe_titles(*, limit: int = 5000) -> list[str]:
    """Titles from the crawled @britishpathe YouTube hub (for Pathé name→URL)."""
    limit = max(1, min(int(limit), 100_000))
    with db() as conn:
        rows = conn.execute(
            """
            SELECT title FROM queue_items
            WHERE url LIKE '%youtube.com%'
              AND hub_url LIKE '%britishpathe%'
              AND title IS NOT NULL
              AND TRIM(title) != ''
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        t = (r["title"] or "").strip()
        if not t:
            continue
        key = t.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def queue_stats_pathe() -> dict:
    """Queue counters scoped to britishpathe.com URLs (fresh-pending semantics)."""
    agg = _queue_aggregate(_PATHE_URL_SQL)
    return {
        "n_queue": agg["n_queue"],
        "n_pending": agg["n_pending_fresh"],
        "n_active": agg["n_active_q"],
        "n_done": agg["n_done"],
        "n_error": agg["n_error"],
    }


def list_queue_page_pathe(
    *,
    offset: int = 0,
    limit: int = 100,
    status: str = "",
    q: str = "",
) -> dict:
    return list_queue_page(offset=offset, limit=limit, status=status, q=q, source="pathe")


def set_queue_status(item_id: int, status: str, error: str = "", detail: str = "") -> None:
    # #region agent log
    from logutil import agent_dbg

    t0 = time.time()
    got_lock = _DB_WRITE_LOCK.acquire(timeout=0.0)
    if got_lock:
        _DB_WRITE_LOCK.release()
    agent_dbg(
        "D",
        "db.py:set_queue_status",
        "enter set_queue_status",
        {
            "item_id": item_id,
            "status": status,
            "detail": (detail or "")[:80],
            "lock_free": bool(got_lock),
        },
        tid=True,
    )
    # #endregion
    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            with db(write=True) as conn:
                conn.execute(
                    "UPDATE queue_items SET status=?, error=?, detail=? WHERE id=?",
                    (status, (error or "")[:1000], (detail or "")[:500], item_id),
                )
            last_err = None
            break
        except Exception as e:
            last_err = e
            time.sleep(0.15 * attempt)
    if last_err is not None:
        raise RuntimeError(f"set_queue_status_failed:{last_err}") from last_err
    # #region agent log
    from logutil import agent_dbg

    agent_dbg(
        "D",
        "db.py:set_queue_status",
        "exit set_queue_status",
        {
            "item_id": item_id,
            "status": status,
            "elapsed_ms": int((time.time() - t0) * 1000),
        },
        tid=True,
    )
    # #endregion


def insert_candidates(rows: list[dict]) -> int:
    """Insert candidates and persist stills locally for Review.

    Rows may include ``still_b64`` / ``image_b64`` / ``_local_still``; those are
    saved under ``output/contact_sheets/cand_{id}.jpg`` (not kept in SQLite).
    Missing stills are queued for background frame extract from source video.
    """
    from still_ensure import enqueue_ensure_still, kick_backfill_missing_stills
    from still_store import save_candidate_still

    now = time.time()
    need_ensure: list[dict] = []
    with db(write=True) as conn:
        for r in rows:
            cur = conn.execute(
                """INSERT INTO candidates
                   (video_id, start_sec, end_sec, peak_score, mean_score, rank_score,
                    hit_count, best_cue, source_url, image_url, decision, notes, label, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?)""",
                (
                    r.get("video_id"),
                    r.get("start_sec"),
                    r.get("end_sec"),
                    r.get("peak_score"),
                    r.get("mean_score"),
                    r.get("rank_score"),
                    r.get("hit_count"),
                    r.get("best_cue"),
                    r.get("source_url"),
                    r.get("image_url"),
                    (r.get("notes") or "")[:1000],
                    r.get("label") or "orthodox_dress_candidate_not_identity",
                    now,
                ),
            )
            cid = int(cur.lastrowid)
            try:
                # ONLY local bytes/paths inside the write lock. Never download Pathé/YouTube
                # here — ensure_candidate_still(download_video=True) held this lock for
                # minutes and froze the entire scrape (queue status + job counters stuck).
                saved = save_candidate_still(
                    cid,
                    path=r.get("_local_still") or r.get("local_still"),
                    b64=r.get("still_b64") or r.get("image_b64"),
                    image_url=None,
                )
                if saved is None:
                    note = (r.get("notes") or "").strip()
                    if "no_still_bytes" not in note:
                        conn.execute(
                            "UPDATE candidates SET notes=? WHERE id=?",
                            ((f"no_still_bytes {note}".strip())[:1000], cid),
                        )
                    need_ensure.append(
                        {
                            "id": cid,
                            "source_url": r.get("source_url"),
                            "video_id": r.get("video_id"),
                            "start_sec": r.get("start_sec"),
                            "end_sec": r.get("end_sec"),
                            "image_url": r.get("image_url"),
                        }
                    )
            except Exception as e:
                try:
                    note = (r.get("notes") or "").strip()
                    conn.execute(
                        "UPDATE candidates SET notes=? WHERE id=?",
                        ((f"{note} still_save_err:{e}"[:200]).strip()[:1000], cid),
                    )
                except Exception:
                    pass
                need_ensure.append(
                    {
                        "id": cid,
                        "source_url": r.get("source_url"),
                        "video_id": r.get("video_id"),
                        "start_sec": r.get("start_sec"),
                        "end_sec": r.get("end_sec"),
                        "image_url": r.get("image_url"),
                    }
                )
    # Outside the write lock — queue extracts + kick grouped video backfill.
    for row in need_ensure:
        enqueue_ensure_still(row)
    if need_ensure:
        kick_backfill_missing_stills(limit=max(200, len(need_ensure) * 4))
    return len(rows)


def list_candidates(limit: int = 2000) -> list[dict]:
    from still_ensure import enqueue_ensure_still
    from still_store import local_crop_url, local_still_url, local_strip_url, save_candidate_still

    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM candidates ORDER BY rank_score DESC LIMIT ?", (limit,)
        ).fetchall()
    crop_status_fn = None
    try:
        from frame_strip import crop_status as crop_status_fn
    except Exception:
        crop_status_fn = None
    out = []
    for i, r in enumerate(rows, 1):
        d = dict(r)
        d["rank"] = i
        d["key"] = f"{d['id']}"
        # Prefer durable local still; ignore Catbox / other cloud hosts.
        local = local_still_url(d["id"])
        cloud = (d.get("image_url") or "").strip()
        if cloud and "catbox" in cloud.lower():
            cloud = ""
            d["image_url"] = ""
        if not local and cloud.startswith(("http://", "https://")):
            # Rare legacy non-catbox URL — hydrate into contact_sheets/ once.
            try:
                if save_candidate_still(int(d["id"]), image_url=cloud):
                    local = local_still_url(d["id"])
            except Exception:
                pass
        if not local:
            enqueue_ensure_still(d)
        if local:
            d["contact_url"] = local
        else:
            d["contact_url"] = None
        d["strip_url"] = local_strip_url(d["id"])
        d["crop_url"] = local_crop_url(d["id"])
        if crop_status_fn is not None:
            st = crop_status_fn(d["id"])
            d["crop_status"] = st.get("status") or "none"
            d["crop_error"] = st.get("error")
            if st.get("crop_url"):
                d["crop_url"] = st["crop_url"]
        else:
            d["crop_status"] = "ready" if d["crop_url"] else "none"
            d["crop_error"] = None
        d["source_path"] = ""
        d["video_url"] = ""
        out.append(d)
    return out


def candidate_stats() -> dict:
    with db() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM candidates").fetchone()["n"]
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM candidates WHERE decision IS NULL OR decision=''"
        ).fetchone()["n"]
        accepted = conn.execute(
            "SELECT COUNT(*) AS n FROM candidates WHERE decision='accept'"
        ).fetchone()["n"]
        videos = conn.execute(
            "SELECT COUNT(DISTINCT video_id) AS n FROM candidates"
        ).fetchone()["n"]
    return {
        "n_candidates": n,
        "n_pending": pending,
        "n_accepted": accepted,
        "videos_scanned": videos,
    }


def update_review(cand_id: int, decision: str, notes: str) -> None:
    with db(write=True) as conn:
        # Preserve OpenAI keep/drop tag so Review gating survives human note edits.
        prev = conn.execute("SELECT notes FROM candidates WHERE id=?", (cand_id,)).fetchone()
        prev_notes = str(prev["notes"] or "") if prev else ""
        new_notes = notes or ""
        low_new = new_notes.lower()
        for prefix in ("openai:keep", "openai:drop", "openai:uncertain"):
            if prefix in prev_notes.lower() and prefix not in low_new:
                tag = next(
                    (
                        ln
                        for ln in prev_notes.splitlines()
                        if ln.strip().lower().startswith(prefix)
                    ),
                    prefix,
                )
                new_notes = f"{tag}\n{new_notes}".strip()
                low_new = new_notes.lower()
                break
        conn.execute(
            "UPDATE candidates SET decision=?, notes=? WHERE id=?",
            (decision, new_notes, cand_id),
        )


def clear_candidates() -> None:
    with db(write=True) as conn:
        conn.execute("DELETE FROM candidates")


def clear_train_clips(*, query: str | None = None) -> int:
    """Delete training clips. Pass query to clear one search; omit to wipe all."""
    with db(write=True) as conn:
        if query is None or not str(query).strip():
            cur = conn.execute("DELETE FROM train_clips")
        else:
            cur = conn.execute(
                "DELETE FROM train_clips WHERE query=?",
                (str(query).strip(),),
            )
        return int(cur.rowcount or 0)


def upsert_train_clips(items: list[dict], *, query: str = "rabbi") -> dict:
    """Insert Pathé training clips; skip duplicates. Returns n_added / n_skipped."""
    q = (query or "rabbi").strip() or "rabbi"
    added = 0
    skipped = 0
    now = time.time()
    with db(write=True) as conn:
        for it in items or []:
            url = (it.get("url") or "").strip()
            if not url:
                skipped += 1
                continue
            asset_id = (it.get("identifier") or it.get("asset_id") or "").strip()
            if not asset_id:
                m = re.search(r"/asset/(\d+)", url)
                asset_id = m.group(1) if m else url
            title = (it.get("title") or "").strip()
            year = (it.get("year") or "").strip()
            thumb = (it.get("thumb_url") or it.get("image_url") or "").strip()
            cur = conn.execute(
                """INSERT OR IGNORE INTO train_clips
                   (asset_id, url, title, year, query, thumb_url, decision, notes, created_at, labeled_at)
                   VALUES (?, ?, ?, ?, ?, ?, '', '', ?, NULL)""",
                (asset_id, url, title, year, q, thumb, now),
            )
            if cur.rowcount:
                added += 1
                if thumb:
                    conn.execute(
                        "UPDATE train_clips SET thumb_url=? WHERE url=? AND (thumb_url IS NULL OR thumb_url='')",
                        (thumb, url),
                    )
            else:
                skipped += 1
                if thumb:
                    conn.execute(
                        "UPDATE train_clips SET thumb_url=? WHERE url=? AND (thumb_url IS NULL OR thumb_url='')",
                        (thumb, url),
                    )
                if title:
                    conn.execute(
                        "UPDATE train_clips SET title=? WHERE url=? AND (title IS NULL OR title='' OR title LIKE 'Asset %')",
                        (title, url),
                    )
    return {"n_added": added, "n_skipped": skipped}


def update_train_thumbs(items: list[dict]) -> int:
    """Fill missing thumb_url values from parsed listing rows. Returns n_updated."""
    updated = 0
    with db(write=True) as conn:
        for it in items or []:
            thumb = (it.get("thumb_url") or it.get("image_url") or "").strip()
            if not thumb:
                continue
            url = (it.get("url") or "").strip()
            asset_id = (it.get("identifier") or it.get("asset_id") or "").strip()
            if url:
                cur = conn.execute(
                    "UPDATE train_clips SET thumb_url=? "
                    "WHERE url=? AND (thumb_url IS NULL OR thumb_url='')",
                    (thumb, url),
                )
            elif asset_id:
                cur = conn.execute(
                    "UPDATE train_clips SET thumb_url=? "
                    "WHERE asset_id=? AND (thumb_url IS NULL OR thumb_url='')",
                    (thumb, asset_id),
                )
            else:
                continue
            updated += int(cur.rowcount or 0)
    return updated


def list_train_clips(
    *,
    query: str = "rabbi",
    status: str = "",
    q: str = "",
    limit: int = 2000,
    offset: int = 0,
) -> dict:
    """List training clips for a Pathé search query."""
    query_s = (query or "rabbi").strip() or "rabbi"
    status_s = (status or "").strip().lower()
    search = (q or "").strip().lower()
    limit = max(1, min(int(limit or 2000), 5000))
    offset = max(0, int(offset or 0))
    where = ["query=?"]
    args: list[Any] = [query_s]
    if status_s in ("pending", "unlabeled", ""):
        if status_s in ("pending", "unlabeled"):
            where.append("(decision IS NULL OR decision='')")
    elif status_s in ("yes", "orthodox", "accept"):
        where.append("decision='yes'")
    elif status_s in ("no", "reject", "not"):
        where.append("decision='no'")
    if search:
        where.append("(LOWER(title) LIKE ? OR LOWER(url) LIKE ? OR asset_id LIKE ?)")
        like = f"%{search}%"
        args.extend([like, like, like])
    clause = " AND ".join(where)
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM train_clips WHERE {clause}", args
        ).fetchone()["n"]
        rows = conn.execute(
            f"""SELECT * FROM train_clips WHERE {clause}
                ORDER BY
                  CASE WHEN decision IS NULL OR decision='' THEN 0 ELSE 1 END,
                  id ASC
                LIMIT ? OFFSET ?""",
            (*args, limit, offset),
        ).fetchall()
        stats = conn.execute(
            """SELECT
                 COUNT(*) AS n_total,
                 SUM(CASE WHEN decision IS NULL OR decision='' THEN 1 ELSE 0 END) AS n_pending,
                 SUM(CASE WHEN decision='yes' THEN 1 ELSE 0 END) AS n_yes,
                 SUM(CASE WHEN decision='no' THEN 1 ELSE 0 END) AS n_no
               FROM train_clips WHERE query=?""",
            (query_s,),
        ).fetchone()
    return {
        "clips": [dict(r) for r in rows],
        "total": int(total or 0),
        "offset": offset,
        "limit": limit,
        "stats": {
            "n_total": int(stats["n_total"] or 0),
            "n_pending": int(stats["n_pending"] or 0),
            "n_yes": int(stats["n_yes"] or 0),
            "n_no": int(stats["n_no"] or 0),
        },
    }


def update_train_label(
    *,
    clip_id: int | None = None,
    url: str = "",
    decision: str,
    notes: str = "",
) -> dict:
    """Set Orthodox-Jew training label: yes / no / '' (clear)."""
    dec = (decision or "").strip().lower()
    if dec in ("accept", "orthodox", "keep", "true", "1"):
        dec = "yes"
    elif dec in ("reject", "not", "pass", "false", "0"):
        dec = "no"
    elif dec in ("clear", "undo", "skip"):
        dec = ""
    elif dec not in ("yes", "no", ""):
        raise ValueError("decision must be yes, no, or clear")
    notes_s = notes or ""
    labeled_at = time.time() if dec else None
    with db(write=True) as conn:
        if clip_id is not None:
            conn.execute(
                "UPDATE train_clips SET decision=?, notes=?, labeled_at=? WHERE id=?",
                (dec, notes_s, labeled_at, int(clip_id)),
            )
            row = conn.execute(
                "SELECT * FROM train_clips WHERE id=?", (int(clip_id),)
            ).fetchone()
        else:
            u = (url or "").strip()
            if not u:
                raise ValueError("missing clip id or url")
            conn.execute(
                "UPDATE train_clips SET decision=?, notes=?, labeled_at=? WHERE url=?",
                (dec, notes_s, labeled_at, u),
            )
            row = conn.execute(
                "SELECT * FROM train_clips WHERE url=?", (u,)
            ).fetchone()
    if not row:
        raise KeyError("train clip not found")
    return dict(row)
