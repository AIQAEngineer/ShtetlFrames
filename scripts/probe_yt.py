import cv2
import os

cap = cv2.VideoCapture(r"data\videos\kolbuszowa_yt.mp4")
out = r"output\kolbuszowa_cards"
os.makedirs(out, exist_ok=True)
for t in (540, 549, 1060, 1072, 1100, 1115, 1200, 1217):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    print(t, ok)
    if ok:
        cv2.imwrite(os.path.join(out, f"probe_{t:04d}s.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
print("done")
