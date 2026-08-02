"""Park known-dead / undownloadable queue hosts so scrape only claims usable video.

- videocinecitta.bytewise.it: mass HTTP 404 on EFG embedded MP4s
- fn.org.pl: host down (re-apply park)
- Europeana provider *pages* (not direct media, not YouTube/INA, not EUScreen/IWM):
  set downloadable='no' so take_pending skips them until a resolver exists

Does not delete rows. Requeue later by clearing parked errors / flipping downloadable.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "output" / "shtetlframes.db"

# Direct-media / known-good patterns we keep claimable among Europeana/EFG.
KEEP_URL_SQL = """
  url LIKE '%.mp4%'
  OR url LIKE '%.webm%'
  OR url LIKE '%.m3u8%'
  OR url LIKE '%youtube.com%'
  OR url LIKE '%youtu.be%'
  OR url LIKE '%ina.fr%'
  OR url LIKE '%euscreen.eu%'
  OR url LIKE '%iwm.org.uk%'
  OR url LIKE '%filmportal.de%'
  OR url LIKE '%nfa.cz%'
  OR url LIKE '%cinememoire.net%'
  OR url LIKE '%britishpathe.com%'
  OR url LIKE '%openbeelden.nl%'
  OR url LIKE '%digilab.nfa.cz%'
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    con = sqlite3.connect(str(DB), timeout=60)
    con.row_factory = sqlite3.Row

    # 1) Dead Cinecittà / bytewise CDN
    cur = con.execute(
        "UPDATE queue_items SET status='error', attempts=99, "
        "error='parked: videocinecitta.bytewise.it 404 (2026-08-02)' "
        "WHERE status IN ('queued','pending','scanning','downloading','uploading') "
        "AND (url LIKE '%videocinecitta.bytewise.it%' OR url LIKE '%bytewise.it%')"
    )
    n_cine = cur.rowcount
    con.commit()
    print(f"parked videocinecitta/bytewise: {n_cine}")

    # 2) Polish FN archive host down
    cur = con.execute(
        "UPDATE queue_items SET status='error', attempts=99, "
        "error='parked: fn.org.pl host down (2026-08-02)' "
        "WHERE status IN ('queued','pending','scanning','downloading','uploading') "
        "AND url LIKE '%fn.org.pl%'"
    )
    n_fn = cur.rowcount
    con.commit()
    print(f"parked fn.org.pl: {n_fn}")

    # 3) Europeana catalog/player pages without a known path to media
    cur = con.execute(
        f"""
        UPDATE queue_items
        SET downloadable='no',
            detail='gated: europeana provider page (no direct media / no resolver)'
        WHERE source LIKE 'europeana%'
          AND downloadable='yes'
          AND status IN ('queued','pending','scanning','error')
          AND NOT ({KEEP_URL_SQL})
        """
    )
    n_eu = cur.rowcount
    con.commit()
    print(f"gated europeana provider pages (downloadable=no): {n_eu}")

    # 4) EFG linked_out / non-media leftovers that aren't in keep list
    cur = con.execute(
        f"""
        UPDATE queue_items
        SET downloadable='no',
            detail='gated: efg non-media / no known host'
        WHERE source LIKE 'efg%'
          AND downloadable='yes'
          AND status IN ('queued','pending','scanning','error')
          AND NOT ({KEEP_URL_SQL})
          AND url NOT LIKE '%videocinecitta%'
          AND url NOT LIKE '%bytewise.it%'
        """
    )
    n_efg = cur.rowcount
    con.commit()
    print(f"gated efg non-media: {n_efg}")

    # Summary of what remains claimable
    row = con.execute(
        """
        SELECT COUNT(*) AS n FROM queue_items
        WHERE downloadable='yes'
          AND status IN ('pending','queued','scanning','error')
          AND NOT (status='error' AND COALESCE(attempts,0) >= 5)
        """
    ).fetchone()
    print(f"still claimable (approx): {row['n']}")

    print("--- top remaining claimable hosts ---")
    hosts = con.execute(
        """
        SELECT
          CASE
            WHEN instr(url, '://') > 0 THEN
              lower(substr(url, instr(url, '://')+3,
                CASE WHEN instr(substr(url, instr(url, '://')+3), '/') > 0
                  THEN instr(substr(url, instr(url, '://')+3), '/')-1
                  ELSE length(substr(url, instr(url, '://')+3)) END))
            ELSE '?'
          END AS host,
          COUNT(*) AS n
        FROM queue_items
        WHERE downloadable='yes'
          AND status IN ('pending','queued','scanning')
        GROUP BY host
        ORDER BY n DESC
        LIMIT 20
        """
    ).fetchall()
    for h in hosts:
        print(f"  {h['n']:5d}  {h['host']}")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
