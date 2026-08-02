"""Sample the full pathe_259561.mp4 into timestamped contact sheets."""
import cv2
import math
import os

SRC = r"data\videos\pathe_259561.mp4"
OUT = r"output\pathe_259561_map"
STEP_S = 10.0
COLS, ROWS = 5, 4
CELL_W, CELL_H = 320, 240
LABEL_H = 22

os.makedirs(OUT, exist_ok=True)
cap = cv2.VideoCapture(SRC)
fps = cap.get(cv2.CAP_PROP_FPS)
total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
dur = total / fps
print(f"fps={fps} frames={total} dur={dur:.1f}s")

frames = []
t = 0.0
while t < dur:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    if not ok:
        break
    img = cv2.resize(img, (CELL_W, CELL_H))
    mm, ss = divmod(int(t), 60)
    label = f"{mm:02d}:{ss:02d}  ({int(t)}s)"
    canvas = cv2.copyMakeBorder(img, LABEL_H, 0, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    cv2.putText(canvas, label, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
    frames.append(canvas)
    t += STEP_S

per = COLS * ROWS
for s in range(math.ceil(len(frames) / per)):
    chunk = frames[s * per:(s + 1) * per]
    while len(chunk) < per:
        chunk.append(cv2.copyMakeBorder(
            cv2.resize(cap.read()[1] if False else __import__("numpy").zeros((CELL_H, CELL_W, 3), "uint8"),
                       (CELL_W, CELL_H)), LABEL_H, 0, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0)))
    rows = []
    for r in range(ROWS):
        rows.append(cv2.hconcat(chunk[r * COLS:(r + 1) * COLS]))
    sheet = cv2.vconcat(rows)
    path = os.path.join(OUT, f"sheet_{s:02d}.jpg")
    cv2.imwrite(path, sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("wrote", path)
