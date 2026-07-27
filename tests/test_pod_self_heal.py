"""Pod self-heal helpers."""

from runpod_client import pod_id_from_proxy_url


def test_pod_id_from_proxy_url():
    assert (
        pod_id_from_proxy_url("https://abc123def456-8000.proxy.runpod.net")
        == "abc123def456"
    )
    assert pod_id_from_proxy_url("https://abc123def456-8000.proxy.runpod.net/") == (
        "abc123def456"
    )
    assert pod_id_from_proxy_url("") is None
    assert pod_id_from_proxy_url("https://example.com") is None


def test_scan_import_resilient():
    """scan.py must import even if cues lacks MIN_PERSON_ASPECT (getattr fallback)."""
    import shtetl_core.scan as scan

    assert float(scan.MIN_PERSON_ASPECT) >= 1.0
    assert int(scan.MIN_PERSON_HEIGHT) > 0
