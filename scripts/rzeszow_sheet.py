import cv2
import numpy as np
import os

cap = cv2.VideoCapture(r"data\videos\kolbuszowa_yt.mp4")
out = r"output\kolbuszowa_cards"
cells = []
for t in range(1040, 1301, 2):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    if not ok:
        continue
    img = cv2.resize(img, (320, 240))
    canvas = cv2.copyMakeBorder(img, 20, 0, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    mm, ss = divmod(t, 60)
    cv2.putText(canvas, f"{mm:02d}:{ss:02d} {t}s", (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    cells.append(canvas)
COLS, ROWS = 5, 3
per = COLS * ROWS
for s in range((len(cells) + per - 1) // per):
    chunk = cells[s * per:(s + 1) * per]
    while len(chunk) < per:
        chunk.append(np.zeros((260, 320, 3), np.uint8))
    rows = [cv2.hconcat(chunk[r * COLS:(r + 1) * COLS]) for r in range(ROWS)]
    cv2.imwrite(os.path.join(out, f"rz_sheet_{s}.jpg"), cv2.vconcat(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
print("done", (len(cells) + per - 1) // per, "sheets")
