"""Provider media resolvers: item page URL -> direct playable media URL.

Hosts where yt-dlp is broken/blocked or we want a stable direct stream:

- euscreen.eu          -> euscreen.py   (LouServlet setVideo)
- iwm.org.uk           -> iwm.py        (Scrapfly + rackcdn MP4)
- filmarkivet.se       -> filmarkivet.py (JW Player → S3 MP4)
- tv.nrk.no            -> nrk.py        (psapi → HLS)
- av.tib.eu            -> tib.py        (JWT HLS)
- patrimonio.archivioluce.com -> luce.py (CDN HLS playlist)
- elonet.finna.fi      -> elonet.py     (Finna → Icareus HLS)
- urn.nb.no / nb.no    -> nb_no.py      (IIIF → wow.nb.no HLS)

Used just-in-time by download_entry (local) and process_video_remote (RunPod),
so queue rows keep their canonical item-page URLs and tickets never go stale.
"""

from __future__ import annotations

from typing import Callable

Resolver = tuple[Callable[[str], bool], Callable[[str], str | None], str]

_RESOLVERS: list[Resolver] | None = None


def _registry() -> list[Resolver]:
    global _RESOLVERS
    if _RESOLVERS is not None:
        return _RESOLVERS
    from elonet import is_elonet_url
    from elonet import resolve_media_url as elonet_resolve
    from euscreen import is_euscreen_url
    from euscreen import resolve_media_url as euscreen_resolve
    from filmarkivet import is_filmarkivet_url
    from filmarkivet import resolve_media_url as filmarkivet_resolve
    from iwm import is_iwm_url
    from iwm import resolve_media_url as iwm_resolve
    from luce import is_luce_url
    from luce import resolve_media_url as luce_resolve
    from nb_no import is_nb_url
    from nb_no import resolve_media_url as nb_resolve
    from nrk import is_nrk_url
    from nrk import resolve_media_url as nrk_resolve
    from tib import is_tib_url
    from tib import resolve_media_url as tib_resolve

    _RESOLVERS = [
        (is_euscreen_url, euscreen_resolve, "euscreen"),
        (is_iwm_url, iwm_resolve, "iwm"),
        (is_filmarkivet_url, filmarkivet_resolve, "filmarkivet"),
        (is_nrk_url, nrk_resolve, "nrk"),
        (is_tib_url, tib_resolve, "tib"),
        (is_luce_url, luce_resolve, "luce"),
        (is_elonet_url, elonet_resolve, "elonet"),
        (is_nb_url, nb_resolve, "nb"),
    ]
    return _RESOLVERS


def needs_resolve(url: str) -> bool:
    return any(match(url) for match, _, _ in _registry())


def resolve_media_url(url: str) -> str | None:
    for match, resolve, _name in _registry():
        if match(url):
            return resolve(url)
    return None


def resolver_name(url: str) -> str | None:
    for match, _resolve, name in _registry():
        if match(url):
            return name
    return None


def resolvable_host(url: str) -> bool:
    """True if this URL is handled by a custom provider resolver."""
    return needs_resolve(url)
