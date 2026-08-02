"""Unit tests for provider_html extract helpers (no network)."""

from __future__ import annotations

from provider_html import extract_jw_file, extract_vimeo, extract_youtube


def test_youtube_nocookie_www_data_src():
    html = (
        '<iframe data-src="https://www.youtube-nocookie.com/embed/i0Jr_Mfgoj4'
        '?wmode=opaque&amp;controls="></iframe>'
    )
    assert extract_youtube(html) == "https://www.youtube.com/watch?v=i0Jr_Mfgoj4"


def test_vimeo_json_escaped_slashes():
    html = r'{&quot;embed&quot;:&quot;https:\/\/player.vimeo.com\/video\/651038580?app_id=1&quot;}'
    assert extract_vimeo(html) == "https://player.vimeo.com/video/651038580"


def test_jw_file_skips_commented():
    html = """
    sources: [{
        //file: "https://s3.example/old.mp4"
        file: "https://s3.example/new.mp4"
    }]
    """
    assert extract_jw_file(html) == "https://s3.example/new.mp4"


def test_provider_registry_covers_hosts():
    from provider_resolvers import can_import_provider_page, needs_resolve

    assert needs_resolve("https://www.filmportal.de/node/1")
    assert needs_resolve("https://www.iwm.org.uk/collections/item/object/1")
    assert needs_resolve("https://www.filmmuseum.at/jart/prj3/filmmuseum/main.jart?x=1")
    assert needs_resolve("https://urn.nb.no/URN:NBN:no-nb_video_3264")
    assert needs_resolve("http://mediawien-film.at/film/84/")
    assert can_import_provider_page("https://movingimage.nls.uk/film/1062")
    assert can_import_provider_page("https://vimeo.com/123")
    assert not can_import_provider_page("https://www.kinoteka.org.rs/foo")
