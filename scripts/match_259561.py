"""Match Pathé crowd-scene frames into the Kolbuszowa YT film + extract YT intertitles."""
import cv2
import numpy as np
import os

YT = r"data\videos\kolbuszowa_yt.mp4"
OUT = r"output\kolbuszowa_cards"
os.makedirs(OUT, exist_ok=True)

def ahash(img, size=16):
    g = cv2.cvtColor(cv2.resize(img, (size, size)), cv2.COLOR_BGR2GRAY)
    return (g > g.mean()).flatten()

refs = []
for f in ("full_0886s.jpg", "full_0890s.jpg", "full_0918s.jpg", "full_0930s.jpg"):
    img = cv2.imread(os.path.join(r"output\pathe_259561_detail", f))
    if img is not None:
        refs.append((f, ahash(img)))
print(f"{len(refs)} reference frames")

cap = cv2.VideoCapture(YT)
fps = cap.get(cv2.CAP_PROP_FPS)
dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
print(f"dur {dur:.0f}s")

best = [([],) for _ in refs]  # list of (dist, t) per ref
cards = []
t = 0.0
while t < dur:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    if not ok:
        break
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dark = float((g < 60).mean())
    bright = float((g > 180).mean())
    if dark > 0.55 and 0.005 < bright < 0.5:
        cards.append(t)
    h = ahash(img)
    for i, (name, rh) in enumerate(refs):
        d = int(np.count_nonzero(h != rh))
        lst = best[i][0]
        lst.append((d, t))
        lst.sort()
        del lst[8:]
    t += 1.0

for i, (name, _) in enumerate(refs):
    print(name, "best:", [(d, round(tt, 1)) for d, tt in best[i][0][:6]])

# group card events
events = []
for c in cards:
    if events and c - events[-1][-1] > 1.5:
        events.append([])
    if not events:
        events.append([c])
    else:
        events[-1].append(c)
print(f"{len(events)} card events")
for i, ev in enumerate(events):
    mid = (ev[0] + ev[-1]) / 2
    cap.set(cv2.CAP_PROP_POS_MSEC, mid * 1000)
    ok, img = cap.read()
    if ok:
        mm, ss = divmod(int(mid), 60)
        cv2.imwrite(os.path.join(OUT, f"yt_{i:02d}_{int(mid):04d}s_{mm:02d}m{ss:02d}s.jpg"), img)
        print(f"{i:02d} {ev[0]:7.1f}-{ev[-1]:7.1f} mid={mid:7.1f}")
