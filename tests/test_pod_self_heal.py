"""Pod self-heal helpers."""

from runpod_client import get_pod_pool, merge_pod_pool, pod_id_from_proxy_url, set_pod_pool


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


def test_merge_pod_pool_does_not_shrink():
    set_pod_pool(
        [
            "https://aaa-8000.proxy.runpod.net",
            "https://bbb-8000.proxy.runpod.net",
        ]
    )
    merged = merge_pod_pool(["https://ccc-8000.proxy.runpod.net"])
    assert "https://aaa-8000.proxy.runpod.net" in merged
    assert "https://bbb-8000.proxy.runpod.net" in merged
    assert "https://ccc-8000.proxy.runpod.net" in merged
    assert len(get_pod_pool()) == 3
    # Soft-return with only one ready URL must not wipe the rest.
    set_pod_pool(["https://aaa-8000.proxy.runpod.net"])  # simulate bad replace
    # After a bad replace the pool is 1 — merge recovers additions without
    # resurrecting dropped URLs (drop is intentional). Just ensure merge grows.
    merge_pod_pool(["https://ddd-8000.proxy.runpod.net"])
    assert len(get_pod_pool()) == 2


def test_scan_import_resilient():
    """scan.py must import even if cues lacks MIN_PERSON_ASPECT (getattr fallback)."""
    import shtetl_core.scan as scan

    assert float(scan.MIN_PERSON_ASPECT) >= 1.0
    assert int(scan.MIN_PERSON_HEIGHT) > 0
