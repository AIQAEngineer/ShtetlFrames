"""Extract enhanced crops (frieze, P.P. sign, poster) + fine crowd-sequence sheet."""
import cv2
import numpy as np
import os

SRC = r"data\videos\pathe_259561.mp4"
OUT = r"output\pathe_259561_detail"
os.makedirs(OUT, exist_ok=True)
cap = cv2.VideoCapture(SRC)

def grab(t):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    return img if ok else None

def enhance(img, scale=4):
    up = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    g = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g = clahe.apply(g)
    blur = cv2.GaussianBlur(g, (0, 0), 3)
    sharp = cv2.addWeighted(g, 1.8, blur, -0.8, 0)
    return sharp

# 1) Dump full frames around the crowd scene so we can pick crop regions
for t in range(878, 1001, 2):
    img = grab(t)
    if img is not None:
        cv2.imwrite(os.path.join(OUT, f"full_{t:04d}s.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
print("full frames done")

# 2) Fine contact sheet of the crowd sequence 878-1000, 2s step
cells = []
for t in range(878, 1001, 2):
    img = grab(t)
    if img is None:
        continue
    img = cv2.resize(img, (320, 240))
    canvas = cv2.copyMakeBorder(img, 20, 0, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    mm, ss = divmod(t, 60)
    cv2.putText(canvas, f"{mm:02d}:{ss:02d}", (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
    cells.append(canvas)
COLS, ROWS = 5, 3
per = COLS * ROWS
for s in range((len(cells) + per - 1) // per):
    chunk = cells[s * per:(s + 1) * per]
    while len(chunk) < per:
        chunk.append(np.zeros((260, 320, 3), np.uint8))
    rows = [cv2.hconcat(chunk[r * COLS:(r + 1) * COLS]) for r in range(ROWS)]
    cv2.imwrite(os.path.join(OUT, f"crowd_sheet_{s}.jpg"), cv2.vconcat(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
print("sheets done")
