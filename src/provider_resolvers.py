"""Provider media resolvers: item page URL -> direct playable media URL.

Hosts where yt-dlp is broken/blocked or a cheap local extract beats it:
- euscreen.eu (item.html)     -> euscreen.py     (LouServlet)
- iwm.org.uk (collections)    -> iwm.py          (rackcdn MP4)
- filmportal.de               -> filmportal.py   (progressive MP4 / Vimeo)
- filmdatabase.eyefilm.nl     -> eyefilm.py      (YouTube embed)
- cinemateca.pt               -> cinemateca.py   (Vimeo embed)
- stumfilm.dk                 -> stumfilm.py     (Vimeo embed)
- filmarkivet.se              -> filmarkivet.py  (JWPlayer S3 MP4)
- elonet.finna.fi             -> elonet.py       (CloudFront HLS)
- filmmuseum.at               -> filmmuseum.py   (Vimeo embed)
- mediawien-film.at           -> mediawien.py    (progressive MP4)
- urn.nb.no / nb.no           -> nb.py           (IIIF → Wowza HLS)
- kinoteka / filmoteca / WDR / aamod -> vimeo_pages.py (Vimeo embed)
- cinearchives.org            -> cinearchives.py (Diaz oEmbed MP4)
- cinestore.cinetecadibologna.it -> cinestore.py (progressive FLV)
- movingimage.nls.uk            -> nls.py         (JWPlayer HLS via Scrapfly)

Used just-in-time by download_entry (local) and process_video_remote (RunPod),
so queue rows keep their canonical item-page URLs and tickets never go stale.
"""

from __future__ import annotations

# (is_fn, resolve_fn) — imported lazily inside helpers to keep cold start light.
_RESOLVER_LOADERS = (
    ("euscreen", "is_euscreen_url", "resolve_media_url"),
    ("iwm", "is_iwm_url", "resolve_media_url"),
    ("filmportal", "is_filmportal_url", "resolve_media_url"),
    ("eyefilm", "is_eyefilm_url", "resolve_media_url"),
    ("cinemateca", "is_cinemateca_url", "resolve_media_url"),
    ("stumfilm", "is_stumfilm_url", "resolve_media_url"),
    ("filmarkivet", "is_filmarkivet_url", "resolve_media_url"),
    ("elonet", "is_elonet_url", "resolve_media_url"),
    ("filmmuseum", "is_filmmuseum_url", "resolve_media_url"),
    ("mediawien", "is_mediawien_url", "resolve_media_url"),
    ("nb", "is_nb_url", "resolve_media_url"),
    ("vimeo_pages", "is_vimeo_page_url", "resolve_media_url"),
    ("cinearchives", "is_cinearchives_url", "resolve_media_url"),
    ("cinestore", "is_cinestore_url", "resolve_media_url"),
    ("nls", "is_nls_url", "resolve_media_url"),
)


def _iter_resolvers():
    import importlib

    for mod_name, is_name, resolve_name in _RESOLVER_LOADERS:
        mod = importlib.import_module(mod_name)
        yield getattr(mod, is_name), getattr(mod, resolve_name)


def needs_resolve(url: str) -> bool:
    return any(is_fn(url) for is_fn, _ in _iter_resolvers())


def resolve_media_url(url: str) -> str | None:
    for is_fn, resolve_fn in _iter_resolvers():
        if is_fn(url):
            return resolve_fn(url)
    return None


def resolvable_host(host_or_url: str) -> bool:
    """True if this host/URL is covered by a JIT resolver (for import gating)."""
    u = (host_or_url or "").strip()
    if not u:
        return False
    if "://" not in u:
        u = "https://" + u
    return needs_resolve(u)


# Hosts where queuing the item page and letting yt-dlp handle it is enough
# (no custom resolver). Used by discovery_import for EFG linked_out.
YTDLP_NATIVE_HOSTS = (
    # movingimage.nls.uk → nls.py (WAF blocks plain yt-dlp)
    "vimeo.com",
    "player.vimeo.com",
    "dailymotion.com",
    "dai.ly",
    "youtube.com",
    "youtu.be",
    "www.youtube.com",
)


def is_ytdlp_native_host(host_or_url: str) -> bool:
    from urllib.parse import urlparse

    u = (host_or_url or "").strip()
    if not u:
        return False
    host = urlparse(u if "://" in u else "https://" + u).netloc.lower()
    if host.startswith("www."):
        host_bare = host[4:]
    else:
        host_bare = host
    for h in YTDLP_NATIVE_HOSTS:
        if host == h or host_bare == h or host.endswith("." + h):
            return True
    return False


def can_import_provider_page(url: str) -> bool:
    """Whether an EFG/Europeana linked-out page URL is worth queuing."""
    return needs_resolve(url) or is_ytdlp_native_host(url)
