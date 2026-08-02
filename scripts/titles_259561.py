"""Detect intertitle cards (white text on black) across the full film."""
import cv2
import numpy as np
import os

SRC = r"data\videos\pathe_259561.mp4"
OUT = r"output\pathe_259561_cards"
os.makedirs(OUT, exist_ok=True)

cap = cv2.VideoCapture(SRC)
fps = cap.get(cv2.CAP_PROP_FPS)
dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps

STEP = 0.5
DARK_FRac_MIN = 0.55
hits = []
t = 0.0
while t < dur:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    if not ok:
        break
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dark = float((g < 60).mean())
    bright = float((g > 180).mean())
    # title cards: mostly dark with some bright text pixels
    if dark > DARK_FRac_MIN and 0.005 < bright < 0.5:
        hits.append((t, dark, bright))
    t += STEP

# group into events (gap > 1.5s starts a new event)
events = []
for h in hits:
    if events and h[0] - events[-1][-1][0] > 1.5:
        events.append([])
    events[-1].append(h) if events else events.append([h])

print(f"{len(events)} card events")
for i, ev in enumerate(events):
    start, end = ev[0][0], ev[-1][0]
    mid = (start + end) / 2
    cap.set(cv2.CAP_PROP_POS_MSEC, mid * 1000)
    ok, img = cap.read()
    if not ok:
        continue
    mm, ss = divmod(int(mid), 60)
    name = f"card_{i:02d}_{int(mid):04d}s_{mm:02d}m{ss:02d}s.jpg"
    cv2.imwrite(os.path.join(OUT, name), img)
    print(f"{i:02d}  {start:7.1f}-{end:7.1f}  mid={mid:7.1f}  -> {name}")
