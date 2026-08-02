"""Contact sheets for Pathé East Galicia + crowd section (~9:00-16:30)."""
import cv2
import numpy as np
import os

cap = cv2.VideoCapture(r"data\videos\pathe_259561.mp4")
out = r"output\pathe_259561_galicia"
os.makedirs(out, exist_ok=True)
cells = []
for t in range(540, 1001, 2):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    if not ok:
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
    path = os.path.join(out, f"gal_sheet_{s:02d}.jpg")
    cv2.imwrite(path, cv2.vconcat(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(path)
print("done")
