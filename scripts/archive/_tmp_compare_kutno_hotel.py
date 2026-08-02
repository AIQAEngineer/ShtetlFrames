from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

out = Path("output/pathe_259561_photo_id")
left = Image.open(out / "hotel_1340_enh.jpg").convert("RGB")

H = 720
lw = int(left.width * H / left.height)
left = left.resize((lw, H), Image.Resampling.LANCZOS)

rw = max(lw, 760)
right = Image.new("RGB", (rw, H), (18, 18, 20))
draw = ImageDraw.Draw(right)


def font(size: int):
    for p in (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


title_f = font(28)
body_f = font(22)
small_f = font(18)
mono_f = font(20)

margin = 36
y = 40
draw.text((margin, y), "DIRECTORY MATCH (what was found)", fill=(240, 220, 160), font=title_f)
y += 48
draw.text((margin, y), "Town: Kutno, Poland", fill=(255, 255, 255), font=body_f)
y += 34
draw.text((margin, y), "Address: ul. Sienkiewicza 41", fill=(255, 255, 255), font=body_f)
y += 34
draw.text(
    (margin, y),
    'Owner: Markus Blumenzon  (= film "M. Blumenzon")',
    fill=(255, 255, 255),
    font=body_f,
)
y += 50

draw.rectangle([margin - 8, y - 10, rw - margin + 8, y + 210], outline=(90, 90, 95), width=2)
draw.text(
    (margin, y),
    "1938 / 1939 Spis Abonentow (excl. Warsaw)",
    fill=(180, 200, 255),
    font=small_f,
)
y += 32
draw.text((margin, y), "HOTELE:", fill=(200, 200, 200), font=mono_f)
y += 30
draw.text((margin, y), '"Polski" ... 3 Maja 6', fill=(170, 170, 170), font=mono_f)
y += 28
draw.text((margin, y), '"Staropolski" ... Narutowicza 1', fill=(170, 170, 170), font=mono_f)
y += 28
draw.text(
    (margin, y),
    '"Warszawski", wl. Markus Blumenzon,',
    fill=(255, 230, 140),
    font=mono_f,
)
y += 28
draw.text((margin, y), "              Sienkiewicza 41", fill=(255, 230, 140), font=mono_f)
y += 50

draw.text(
    (margin, y),
    "Also 1928-1930 Ksiega Adresowa Polski — Kutno:",
    fill=(180, 180, 180),
    font=small_f,
)
y += 28
draw.text(
    (margin, y),
    "Pokoje umeblowane: Blumenzon A.; Blumenzon M.",
    fill=(220, 220, 220),
    font=small_f,
)
y += 50
draw.text(
    (margin, y),
    "Note: no surviving period facade photo of #41 found yet.",
    fill=(160, 140, 140),
    font=small_f,
)
y += 26
draw.text(
    (margin, y),
    "ID is from directories, not a visual building match.",
    fill=(160, 140, 140),
    font=small_f,
)

label_h = 48
canvas_w = lw + rw
canvas_h = H + label_h
canvas = Image.new("RGB", (canvas_w, canvas_h), (10, 10, 12))
canvas.paste(left, (0, label_h))
canvas.paste(right, (lw, label_h))
d = ImageDraw.Draw(canvas)
d.rectangle([0, 0, canvas_w, label_h], fill=(30, 30, 34))
d.text(
    (16, 12),
    "Pathe 259561  ~13:40  Hotel Warszawski / M. Blumenzon",
    fill=(255, 255, 255),
    font=small_f,
)
d.text(
    (lw + 16, 12),
    "Evidence: Kutno directories (Genealogy Indexer)",
    fill=(255, 255, 255),
    font=small_f,
)
d.line([(lw, 0), (lw, canvas_h)], fill=(80, 80, 80), width=3)

path = out / "COMPARE_hotel_pathe_vs_kutno_dirs.jpg"
canvas.save(path, quality=92)
print("wrote", path, canvas.size)
