"""Save Hadassah OCR + render readable notice plates + try one image capture."""
import json
import os
import sys
import textwrap
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaufman_notice_scan import KEY, OUT_DIR, scrapfly_text, strip_html

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow", "-q"])
    from PIL import Image, ImageDraw, ImageFont

NOTICES = [
    {
        "date": "24 May 1935",
        "issue": "JW19350524",
        "page": 15,
        "title": "With the Travelers",
        "file": "1935-05-24_travel_notice",
        "url": "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=d&d=JW19350524.2.15",
        "quote": (
            "Among the localites contemplating traveling on a pleasure trip to Europe "
            "are Dr. and Mrs. Bernard Kaufman, their son and daughter, Bernard, Jr., and Joy. "
            "They have booked passage on the Rex, sailing from New York, June 9. "
            "Their destination is Palestine and the itinerary is a leisurely tour of Central Europe. "
            "The family will return for the holidays."
        ),
    },
    {
        "date": "20 December 1935",
        "issue": "JW19351220",
        "page": 14,
        "title": "S. F. Zionist District Plans Entertaining Meeting Jan. 8",
        "file": "1935-12-20_pictures_of_palestine",
        "url": "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=d&d=JW19351220.2.14",
        "quote": (
            "Pictures of Palestine, taken by Dr. Bernard Kaufman during his recent visit there, "
            "will be presented Wednesday evening, January 8, before members of the San Francisco "
            "District of the Zionist Organization at the Jewish Community Center."
        ),
    },
    {
        "date": "27 December 1935",
        "issue": "JW19351227",
        "page": 36,
        "title": "Lav Tovians",
        "file": "1935-12-27_lav_tovians_moving_pictures",
        "url": "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=d&d=JW19351227.2.36",
        "quote": (
            "Palestinian moving pictures and an address on \"Youth in Palestine\" by Bernard Kaufman, Jr., "
            "will feature the installation program of the Lav Tovians, Sunday afternoon, at 2:30, "
            "in the Assembly hall of Temple Beth Israel."
        ),
    },
    {
        "date": "10 January 1936",
        "issue": "JW19360110",
        "page": 55,
        "title": "Temple Emanu-El Pathfinders",
        "file": "1936-01-10_pathfinders_bernard_jr",
        "url": "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=d&d=JW19360110.2.55",
        "quote": (
            "Bernard Kaufman, Jr., who returned from a visit in Palestine with his parents, "
            "will speak on \"Palestine and the Near East\" before Temple Emanu-El Pathfinders, "
            "Sunday evening, at 8:00 o'clock, in the Martin Meyer Memorial Room of the Temple. "
            "He will illustrate his talk with motion pictures of the Jewish Homeland."
        ),
    },
    {
        "date": "31 January 1936",
        "issue": "JW19360131",
        "page": 62,
        "title": "Hadassah's Schedule Of Events",
        "file": "1936-01-31_hadassah_mrs_kaufman",
        "url": "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=d&d=JW19360131.2.62",
        "quote": (
            "At the regular monthly meeting of Oakland chapter, Hadassah, set for Monday, February 3, "
            "Mrs. Bernard Kaufman will present a series of moving pictures of Palestine."
        ),
    },
    {
        "date": "14 February 1936",
        "issue": "JW19360214",
        "page": 84,
        "title": "B'nai B'rith Hillel Foundation Program",
        "file": "1936-02-14_hillel_palestinian_experiences",
        "url": "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=d&d=JW19360214.2.84",
        "quote": (
            "Dr. Bernard Kaufman will be the speaker at B'nai B'rith Hillel Foundation, February 14. "
            "His discourse will be illustrated. Topic: \"Palestinian Experiences\" and folk songs."
        ),
    },
]


def plate(n: dict) -> str:
    w, h = 1400, 900
    img = Image.new("RGB", (w, h), (245, 240, 228))
    draw = ImageDraw.Draw(img)
    try:
        font_t = ImageFont.truetype("georgia.ttf", 36)
        font_b = ImageFont.truetype("georgia.ttf", 28)
        font_s = ImageFont.truetype("georgia.ttf", 20)
    except Exception:
        font_t = font_b = font_s = ImageFont.load_default()
    draw.rectangle([40, 40, w - 40, h - 40], outline=(40, 40, 40), width=3)
    y = 70
    draw.text((70, y), "Emanu-El and the Jewish Journal (San Francisco)", fill=(20, 20, 20), font=font_s)
    y += 40
    draw.text((70, y), n["date"], fill=(20, 20, 20), font=font_t)
    y += 55
    draw.text((70, y), n["title"], fill=(80, 40, 20), font=font_b)
    y += 60
    for line in textwrap.wrap(n["quote"], width=70):
        draw.text((70, y), line, fill=(10, 10, 10), font=font_b)
        y += 40
    y += 30
    draw.text((70, y), f"Source: CDNC · {n['issue']}.2.{n['page']}", fill=(90, 90, 90), font=font_s)
    y += 35
    draw.text((70, y), n["url"], fill=(60, 60, 120), font=font_s)
    path = os.path.join(OUT_DIR, f"{n['file']}_plate.jpg")
    img.save(path, quality=92)
    return path


def save_hadassah_full() -> None:
    url = (
        "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=da&command=getSectionText"
        "&d=JW19360131.2.62&srpos=&f=AJAX&e=-------en--20--1--txt-txIN--------"
    )
    t = strip_html(scrapfly_text(url))
    path = os.path.join(OUT_DIR, "1936-01-31_hadassah_mrs_kaufman_p62_full.txt")
    open(path, "w", encoding="utf-8").write(t)
    print("hadassah:", t[:300])


def write_index() -> None:
    lines = [
        "# Kaufman Palestine / Central Europe newspaper trail",
        "",
        "Source: *Emanu-El and the Jewish Journal* (San Francisco), CDNC jewishweekly.",
        "OCR pulled via Scrapfly ASP (`getSectionText`). Page images are Turnstile-gated;",
        "plates below are transcribed notice cards with persistent CDNC links.",
        "",
    ]
    for n in NOTICES:
        lines += [
            f"## {n['date']} — {n['title']}",
            "",
            f"> {n['quote']}",
            "",
            f"- CDNC: {n['url']}",
            f"- Plate: `{n['file']}_plate.jpg`",
            "",
        ]
    # town talk bonus
    lines += [
        "## 31 January 1936 — Town Talk (bonus)",
        "",
        '> THE BERNARD KAUFMAN\'S will soon need an impresario if they continue to be flooded with engagements to project Palestine on the screen.',
        "",
        "- CDNC: https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=d&d=JW19360131.2.9",
        "",
    ]
    path = os.path.join(OUT_DIR, "NOTICES.md")
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    print("index:", path)


def try_image() -> None:
    """Best-effort maximized viewer screenshot."""
    url = "https://cdnc.ucr.edu/cgi-bin/jewishweekly?a=d&d=JW19350524.2.15"
    scenario = [
        {"click": {"selector": 'button[aria-label="Maximize"]'}},
        {"wait": 12000},
    ]
    params = {
        "key": KEY,
        "url": url,
        "asp": "true",
        "country": "us",
        "render_js": "true",
        "rendering_wait": "3000",
        "screenshot_resolution": "1920x1080",
        "screenshots[v]": "#viewer",
        "js_scenario": json.dumps(scenario),
    }
    api = "https://api.scrapfly.io/scrape?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(api, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        meta = (data.get("result") or {}).get("screenshots", {}).get("v")
        if not meta:
            print("no screenshot", data.get("result", {}).get("error"))
            return
        u = meta["url"] + ("&" if "?" in meta["url"] else "?") + "key=" + KEY
        png = urllib.request.urlopen(u, timeout=60).read()
        path = os.path.join(OUT_DIR, "1935-05-24_travel_notice_viewer_try.png")
        open(path, "wb").write(png)
        print("viewer try:", path, len(png))
    except Exception as e:
        print("viewer try failed:", e)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    save_hadassah_full()
    for n in NOTICES:
        p = plate(n)
        print("plate:", p)
        # refresh OCR sidecar
        open(os.path.join(OUT_DIR, f"{n['file']}_ocr.txt"), "w", encoding="utf-8").write(n["quote"])
    write_index()
    try_image()
    print("OUT_DIR", OUT_DIR)


if __name__ == "__main__":
    sys.exit(main())
