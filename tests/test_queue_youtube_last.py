"""take_pending claims YouTube/youtu.be URLs last (QUEUE_YOUTUBE_LAST=off disables)."""

from __future__ import annotations

import pytest

import db as db_mod

YT1 = "https://www.youtube.com/watch?v=yt1"
EFG_A = "https://media.efg.example/film_a.mp4"
EURO = "https://europeana.example/item/123"
YT2 = "https://youtu.be/yt2"
ERR_B = "https://media.efg.example/film_b.mp4"
YT3 = "https://www.youtube.com/watch?v=yt3"
QUEUED_C = "https://media.efg.example/film_c.mp4"

# (url, status) — insertion order fixes row ids 1..7.
ROWS = [
    (YT1, "pending"),
    (EFG_A, "pending"),
    (EURO, "pending"),
    (YT2, "pending"),
    (ERR_B, "error"),
    (YT3, "error"),
    (QUEUED_C, "queued"),
]


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "queue.db")
    monkeypatch.setattr(db_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.delenv("QUEUE_YOUTUBE_LAST", raising=False)
    monkeypatch.delenv("QUEUE_CLAIM_ORDER", raising=False)
    db_mod.init_db()
    return tmp_path


def _seed(rows=ROWS):
    db_mod.insert_queue_items([{"url": u, "title": u, "source": "test"} for u, _ in rows])
    with db_mod.db(write=True) as conn:
        for url, status in rows:
            if status != "pending":
                conn.execute("UPDATE queue_items SET status=? WHERE url=?", (status, url))


def _urls(rows):
    return [r["url"] for r in rows]


def test_is_youtube_url():
    assert db_mod.is_youtube_url(YT1)
    assert db_mod.is_youtube_url(YT2)
    assert db_mod.is_youtube_url("HTTPS://WWW.YOUTUBE.COM/watch?v=x")
    assert not db_mod.is_youtube_url(EFG_A)
    assert not db_mod.is_youtube_url(EURO)
    assert not db_mod.is_youtube_url("")
    assert not db_mod.is_youtube_url(None)


def test_queue_youtube_last_toggle(temp_db, monkeypatch):
    monkeypatch.delenv("QUEUE_YOUTUBE_LAST", raising=False)
    assert db_mod.queue_youtube_last() is True
    for off in ("off", "no", "0", "false"):
        monkeypatch.setenv("QUEUE_YOUTUBE_LAST", off)
        assert db_mod.queue_youtube_last() is False
    monkeypatch.setenv("QUEUE_YOUTUBE_LAST", "on")
    assert db_mod.queue_youtube_last() is True


def test_queue_youtube_last_from_settings_store(temp_db, monkeypatch):
    monkeypatch.delenv("QUEUE_YOUTUBE_LAST", raising=False)
    from settings_store import ensure_settings_table

    ensure_settings_table()
    assert db_mod.queue_youtube_last() is True
    with db_mod.db(write=True) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) "
            "VALUES ('QUEUE_YOUTUBE_LAST', 'off', 0)"
        )
    assert db_mod.queue_youtube_last() is False


def test_take_pending_youtube_last_default_branch(temp_db):
    _seed()
    got = _urls(db_mod.take_pending(None))
    # Status bands first (pending → queued → error), YouTube last inside each band.
    assert got == [EFG_A, EURO, YT1, YT2, QUEUED_C, ERR_B, YT3]


def test_take_pending_youtube_last_only_pending(temp_db):
    _seed()
    got = _urls(db_mod.take_pending(None, only_pending=True))
    assert got == [EFG_A, EURO, YT1, YT2]


def test_take_pending_limit_claims_non_youtube_first(temp_db):
    _seed()
    got = _urls(db_mod.take_pending(2))
    assert got == [EFG_A, EURO]
    with db_mod.db() as conn:
        statuses = {
            r["url"]: r["status"]
            for r in conn.execute("SELECT url, status FROM queue_items")
        }
    assert statuses[EFG_A] == "queued"
    assert statuses[EURO] == "queued"
    # YouTube rows were skipped by the limit, not claimed.
    assert statuses[YT1] == "pending"
    assert statuses[YT2] == "pending"


def test_take_pending_youtube_last_off_restores_id_order(temp_db, monkeypatch):
    monkeypatch.setenv("QUEUE_YOUTUBE_LAST", "off")
    _seed()
    got = _urls(db_mod.take_pending(None))
    assert got == [YT1, EFG_A, EURO, YT2, QUEUED_C, ERR_B, YT3]


def test_youtube_last_with_claim_from_end(temp_db, monkeypatch):
    monkeypatch.setenv("QUEUE_CLAIM_ORDER", "end")
    _seed()
    got = _urls(db_mod.take_pending(None, only_pending=True))
    # id DESC inside each YouTube band, YouTube still last.
    assert got == [EURO, EFG_A, YT2, YT1]
