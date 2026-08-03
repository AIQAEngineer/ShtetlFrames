"""Filmhíradók Online provider: search-page parsing + player resolve (no network)."""

from __future__ import annotations

import filmhiradok
from filmhiradok import (
    catalog_pages,
    is_filmhiradok_url,
    parse_search_page,
    resolve_media_url,
    resolve_segment,
    watch_id,
)

SEARCH_HTML = """
<div class="search_items">
  <div class="wrapper">
    <div class="search_item">
      <div class="img"><img src="getimage.php?src=mvh-13-01-03&amp;size=small" alt=""/></div>
      <div class="info">
        <span class="date"><strong>1913. augusztus</strong>,  1/3. bejátszás</span>
        <span class="title"><a href="watch.php?id=14730">Repülőverseny (Rákoson)</a></span>
        <div style="clear:left"></div>
        <span class="links"><a href="search.php?q=&amp;ord=3"><strong>25366</strong> megtekintés</a></span>
      </div>
    </div>
    <div class="search_item last">
      <div class="img"><img src="getimage.php?src=kino_riport-01-09&amp;size=small" alt=""/></div>
      <div class="info">
        <span class="date"><strong>1914. május</strong>, Kino Riport 1/9. bejátszás</span>
        <span class="title"><a href="watch.php?id=5226">A Sybill szerzői &quot;izgalomban&quot;</a></span>
        <span class="links"><a href="#"><strong>29209</strong> megtekintés</a></span>
      </div>
    </div>
  </div>
</div>
<div class="pager_container">
  <div class="wrapper">
    <div class="info"><strong>1-10</strong> / összesen 23080 találat</div>
  </div>
</div>
"""

PLAYER_HTML = """
<html><body>
<video id="fo-video" poster="https://filmhiradokonline.hu/keyframe/fo/mvh-0412-02.jpg">
  <source src="https://filmhiradokonline.hu/fo/mvh-0412.mp4" type='video/mp4'>
</video>
<script>
    var start = 82;
    var end =  143;
</script>
</body></html>
"""


def test_parse_search_page_items_and_total():
    items, total = parse_search_page(SEARCH_HTML)
    assert total == 23080
    assert len(items) == 2
    first, last = items
    assert first["url"] == "https://filmhiradokonline.hu/watch.php?id=14730"
    assert first["title"] == "Repülőverseny (Rákoson)"
    assert first["year"] == "1913"
    assert first["views"] == 25366
    assert first["thumb"].endswith("getimage.php?src=mvh-13-01-03&size=small")
    # "search_item last" variant + HTML entities.
    assert last["id"] == "5226"
    assert last["title"] == 'A Sybill szerzői "izgalomban"'
    assert last["series"].startswith("Kino Riport")


def test_parse_search_page_empty():
    items, total = parse_search_page("<html><body>no results</body></html>")
    assert items == []
    assert total == 0


def test_catalog_pages_rounds_up():
    assert catalog_pages(23080) == 2308
    assert catalog_pages(11) == 2
    assert catalog_pages(0) == 1


def test_watch_id_variants():
    assert watch_id("https://filmhiradokonline.hu/watch.php?id=82") == "82"
    assert watch_id("watch.php?id=5226") == "5226"
    assert watch_id("player.php?id=5&x=1") == "5"
    assert watch_id("https://filmhiradokonline.hu/search.php?new") is None
    assert watch_id("") is None


def test_is_filmhiradok_url():
    assert is_filmhiradok_url("https://filmhiradokonline.hu/watch.php?id=82")
    assert not is_filmhiradok_url("https://example.hu/watch.php?id=1")


def test_resolve_segment_parses_player(monkeypatch):
    monkeypatch.setattr(filmhiradok, "_get", lambda url, **kw: PLAYER_HTML)
    filmhiradok._seg_cache.clear()
    seg = resolve_segment("https://filmhiradokonline.hu/watch.php?id=82")
    assert seg is not None
    assert seg["mp4"] == "https://filmhiradokonline.hu/fo/mvh-0412.mp4"
    assert seg["start"] == 82
    assert seg["end"] == 143
    assert seg["poster"].endswith("/keyframe/fo/mvh-0412-02.jpg")
    assert seg["referer"] == "https://filmhiradokonline.hu/watch.php?id=82"
    # Resolver interface returns just the MP4 (cache hit, no second fetch).
    assert resolve_media_url("https://filmhiradokonline.hu/watch.php?id=82") == seg["mp4"]


def test_resolve_segment_missing_source(monkeypatch):
    monkeypatch.setattr(filmhiradok, "_get", lambda url, **kw: "<html>no player</html>")
    filmhiradok._seg_cache.clear()
    assert resolve_segment("https://filmhiradokonline.hu/watch.php?id=99999") is None


def test_provider_registry_covers_filmhiradok():
    from provider_resolvers import can_import_provider_page, needs_resolve

    assert needs_resolve("https://filmhiradokonline.hu/watch.php?id=82")
    assert can_import_provider_page("https://filmhiradokonline.hu/watch.php?id=82")
