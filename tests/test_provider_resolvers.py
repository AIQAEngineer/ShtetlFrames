"""Unit tests for provider resolvers (URL match + offline parsing where possible)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from elonet import extract_record_id, is_elonet_url  # noqa: E402
from filmarkivet import is_filmarkivet_url  # noqa: E402
from luce import is_luce_url  # noqa: E402
from nb_no import extract_urn, is_nb_url  # noqa: E402
from nrk import extract_program_id, is_nrk_url  # noqa: E402
from provider_resolvers import needs_resolve, resolver_name  # noqa: E402
from tib import is_tib_url  # noqa: E402


def test_matchers():
    assert is_filmarkivet_url(
        "https://www.filmarkivet.se/movies/komische-begegnungen/"
    )
    assert is_nrk_url("https://tv.nrk.no/serie/filmavisen/FMAA41000441/08-09-1941")
    assert extract_program_id(
        "https://tv.nrk.no/serie/filmavisen/FMAA41000441/08-09-1941"
    ) == "FMAA41000441"
    assert is_tib_url("https://av.tib.eu/media/16197")
    assert is_luce_url(
        "https://patrimonio.archivioluce.com/luce-web/detail/IL5000038685/2/"
    )
    assert not is_luce_url("https://www.archivioluce.com/")
    assert is_elonet_url("https://elonet.finna.fi/Record/kavi.elonet_elokuva_101153")
    assert (
        extract_record_id("https://elonet.finna.fi/Record/kavi.elonet_elokuva_101153")
        == "kavi.elonet_elokuva_101153"
    )
    assert is_nb_url(
        "https://www.nb.no/items/URN:NBN:no-nb_digifilm_104637_20150126"
    )
    assert (
        extract_urn("https://urn.nb.no/URN:NBN:no-nb_digifilm_104637_20150126")
        == "URN:NBN:no-nb_digifilm_104637_20150126"
    )


def test_dispatcher_names():
    assert (
        resolver_name("https://tv.nrk.no/serie/filmavisen/FMAA41000441/08-09-1941")
        == "nrk"
    )
    assert needs_resolve("https://av.tib.eu/media/16197")
    assert not needs_resolve("https://www.youtube.com/watch?v=abc")
