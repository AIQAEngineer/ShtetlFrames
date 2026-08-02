import cv2
import os

cap = cv2.VideoCapture(r"data\videos\kolbuszowa_yt.mp4")
out = r"output\kolbuszowa_cards"
# dump every 0.5s 1076-1100 to catch the title card, plus building wides
for t in [x / 2 for x in range(2152, 2201)]:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    if ok:
        cv2.imwrite(os.path.join(out, f"rz_{t:07.1f}s.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
print("done")
