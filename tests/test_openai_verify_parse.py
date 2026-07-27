"""Unit tests for OpenAI verdict parsing (no network)."""

from openai_verify import (
    _parse_verdict,
    filter_candidates_openai,
    format_verdict_notes,
    notes_openai_approved,
    notes_openai_dropped,
    notes_openai_uncertain,
    verdict_is_keep,
)
from label_feedback import apply_confidence_gate, min_keep_confidence


def test_parse_keep_json():
    v = _parse_verdict(
        '{"keep": true, "looks_jewish": true, "head_covered": true, "confidence": 0.9, '
        '"reason": "shtreimel and Orthodox dress"}'
    )
    assert v["keep"] is True
    assert v["looks_jewish"] is True
    assert v["head_covered"] is True
    assert v["confidence"] == 0.9
    assert "shtreimel" in v["reason"]
    assert verdict_is_keep(v) is True


def test_parse_drop_json():
    v = _parse_verdict(
        '{"keep": false, "looks_jewish": false, "head_covered": false, '
        '"confidence": 0.8, "reason": "business suit"}'
    )
    assert v["keep"] is False
    assert verdict_is_keep(v) is False


def test_bare_head_hard_reject():
    """Bare head / coat-only must not keep — Jewish head-covering gate."""
    v = _parse_verdict(
        '{"keep": true, "looks_jewish": true, "head_covered": false, "confidence": 0.95, '
        '"reason": "beard and payot, long coat"}'
    )
    assert v["keep"] is False
    assert v["head_covered"] is False
    assert verdict_is_keep(v) is False


def test_looks_jewish_false_rejects_even_with_hat():
    v = _parse_verdict(
        '{"keep": true, "looks_jewish": false, "head_covered": true, "confidence": 0.9, '
        '"reason": "secular man in black fedora"}'
    )
    assert v["keep"] is False
    assert v["looks_jewish"] is False
    assert verdict_is_keep(v) is False


def test_missing_head_covered_rejects():
    v = _parse_verdict(
        '{"keep": true, "confidence": 0.9, "reason": "looks Orthodox Jewish"}'
    )
    assert v["keep"] is False
    assert verdict_is_keep(v) is False


def test_skipped_does_not_pass():
    assert verdict_is_keep({"keep": True, "skipped": True}) is False
    assert verdict_is_keep({"keep": False, "skipped": True}) is False


def test_notes_gate():
    assert notes_openai_approved("openai:keep conf=0.90 Orthodox dress")
    assert not notes_openai_approved("openai:drop conf=0.80 suit")
    assert not notes_openai_approved("")
    assert not notes_openai_approved("human note only")
    assert notes_openai_dropped("openai:drop conf=0.80 suit")
    assert not notes_openai_dropped("openai:keep conf=0.90 Orthodox dress")
    assert notes_openai_uncertain("openai:uncertain conf=0.40 low_conf")
    assert not notes_openai_approved("openai:uncertain conf=0.40 low_conf")
    # Open VLM uses the same Review gates with a vlm: prefix.
    assert notes_openai_approved("vlm:keep conf=0.91 shtreimel")
    assert notes_openai_dropped("vlm:drop conf=0.88 fedora only")
    assert notes_openai_uncertain("vlm:uncertain conf=0.50 maybe")


def test_confidence_gate_low_keep(monkeypatch):
    monkeypatch.setenv("OPENAI_MIN_KEEP_CONF", "0.70")
    v = apply_confidence_gate(
        {
            "keep": True,
            "looks_jewish": True,
            "head_covered": True,
            "confidence": 0.4,
            "reason": "maybe",
            "skipped": False,
        }
    )
    assert v["uncertain"] is True
    assert v["keep"] is False
    assert verdict_is_keep(v) is False
    note = format_verdict_notes(v)
    assert note.startswith("openai:uncertain")


def test_confidence_gate_high_keep(monkeypatch):
    monkeypatch.setenv("OPENAI_MIN_KEEP_CONF", "0.70")
    v = apply_confidence_gate(
        {
            "keep": True,
            "looks_jewish": True,
            "head_covered": True,
            "confidence": 0.9,
            "reason": "clear",
            "skipped": False,
        }
    )
    assert not v.get("uncertain")
    assert v["keep"] is True
    assert verdict_is_keep(v) is True
    note = format_verdict_notes(v)
    assert note.startswith("openai:keep")
    assert "head=yes" in note
    assert "jewish=yes" in note


def test_filter_noop_when_disabled(monkeypatch):
    monkeypatch.setattr("openai_verify.openai_verify_enabled", lambda: False)
    rows = [{"image_url": "https://example.com/a.jpg", "peak_score": 0.2}]
    out = filter_candidates_openai(rows)
    assert len(out) == 1


def test_min_keep_confidence_bounds(monkeypatch):
    monkeypatch.setenv("OPENAI_MIN_KEEP_CONF", "1.5")
    assert min_keep_confidence() == 0.95
    monkeypatch.setenv("OPENAI_MIN_KEEP_CONF", "-1")
    assert min_keep_confidence() == 0.0


def test_format_notes_legacy_vlm_provider():
    """Old Review rows may still carry vlm: notes from prior runs."""
    note = format_verdict_notes(
        {
            "keep": True,
            "looks_jewish": True,
            "head_covered": True,
            "confidence": 0.91,
            "reason": "shtreimel",
            "provider": "vlm",
        }
    )
    assert note.startswith("vlm:keep")


def test_verify_backend_always_openai():
    from openai_verify import verify_backend

    assert verify_backend() == "openai"
