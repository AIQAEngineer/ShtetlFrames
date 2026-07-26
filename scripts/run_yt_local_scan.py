"""One-shot local YouTube training scan (blocks until done)."""
import sys

sys.path.insert(0, "src")

from db import db, get_job, init_db
from pipeline_train import (
    _auto_accept_youtube_ref_candidates,
    load_youtube_train_ref,
    save_youtube_train_ref,
    start_youtube_train_ref,
)

URL = "https://www.youtube.com/watch?v=87XlDRjmPME"


def main() -> None:
    init_db()
    ref = save_youtube_train_ref(URL, title="Orthodox ref")
    from pipeline_scrape import prioritize_queue_url, scan_one_local

    pri = prioritize_queue_url(URL, title="Orthodox look training reference")
    print("priority:", pri)
    with db() as conn:
        row = conn.execute("SELECT * FROM queue_items WHERE url=?", (URL,)).fetchone()
    if not row:
        raise SystemExit("queue row missing")
    from db import set_job

    set_job(
        "train_seed",
        status="running",
        phase="youtube_local",
        message="Local download + scan…",
        progress=20,
        hub_url=URL,
    )
    try:
        hits = scan_one_local(dict(row), status_job="train_seed")
        accepted = _auto_accept_youtube_ref_candidates(ref)
        set_job(
            "train_seed",
            status="done",
            phase="done",
            message=f"Done · {hits} hit(s) · {accepted} tagged Orthodox",
            progress=100,
            hits=hits,
        )
        print(f"OK hits={hits} accepted={accepted} job={get_job('train_seed')}")
    except Exception as e:
        set_job(
            "train_seed",
            status="error",
            phase="error",
            message=str(e)[:200],
            progress=100,
        )
        raise


if __name__ == "__main__":
    main()
