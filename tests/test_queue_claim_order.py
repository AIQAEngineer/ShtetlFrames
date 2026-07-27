"""QUEUE_CLAIM_ORDER start vs end claim direction."""

from db import _queue_id_dir, queue_claim_from_end


def test_queue_claim_from_end_env(monkeypatch):
    monkeypatch.setenv("QUEUE_CLAIM_ORDER", "end")
    assert queue_claim_from_end() is True
    assert _queue_id_dir() == "DESC"


def test_queue_claim_from_start_env(monkeypatch):
    monkeypatch.setenv("QUEUE_CLAIM_ORDER", "start")
    assert queue_claim_from_end() is False
    assert _queue_id_dir() == "ASC"
