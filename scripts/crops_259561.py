"""Crop + enhance frieze, signs, poster from dumped full frames."""
import cv2
import os

D = r"output\pathe_259561_detail"

def enhance(img, scale=6):
    up = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    g = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    g = clahe.apply(g)
    blur = cv2.GaussianBlur(g, (0, 0), 3)
    return cv2.addWeighted(g, 1.9, blur, -0.9, 0)

def crop(src, name, x0, y0, x1, y1, scale=6):
    img = cv2.imread(os.path.join(D, src))
    if img is None:
        print("missing", src)
        return
    c = img[y0:y1, x0:x1]
    cv2.imwrite(os.path.join(D, name), enhance(c, scale))
    print("wrote", name)

# frieze above the arch (wide shot 886s)
crop("full_0886s.jpg", "frieze_886.png", 100, 85, 370, 130, 8)
# frieze from building-crop frame if closer view exists in 884/888/890
for t in (884, 888, 890):
    crop(f"full_{t:04d}s.jpg", f"frieze_{t}.png", 90, 60, 400, 140, 8)
# P.P. sign right edge (890s)
crop("full_0890s.jpg", "sign_pp_890.png", 400, 120, 480, 230, 8)
# poster board lower right (890s)
crop("full_0890s.jpg", "poster_890.png", 360, 190, 480, 300, 8)
# advertising column left (886s)
crop("full_0886s.jpg", "column_886.png", 0, 110, 80, 240, 6)
