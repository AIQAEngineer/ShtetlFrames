"""Build Ultralytics classification dataset from Keep/Pass person crops.

Classes:
  keep  — person crops from Accept labels
  pass  — person crops from Reject labels (hard negatives)

Writes ``output/yolo_ft/cls/{train,val}/{keep,pass}/`` and ``data.yaml``.
Train on GPU (RunPod):

  yolo classify train model=yolov8s-cls.pt data=output/yolo_ft/cls epochs=40 imgsz=224

Then point ``YOLO_WEIGHTS`` at ``output/yolo_ft/cls/runs/.../weights/best.pt``
or copy into ``runpod_worker/``.
"""

from __future__ import annotations

import json
import random
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OnStatus = Callable[[str], None] | None


def yolo_ft_dir() -> Path:
    from config import OUTPUT_DIR

    return OUTPUT_DIR / "yolo_ft" / "cls"


def _person_crops(image: Path, out_dir: Path, *, stem: str, max_crops: int = 3) -> list[Path]:
    """Run stock YOLO person detector; save up to ``max_crops`` crops."""
    try:
        import cv2
        from ultralytics import YOLO
    except Exception:
        return []

    from shtetl_core.cues import YOLO_WEIGHTS

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        model = YOLO(YOLO_WEIGHTS)
        res = model.predict(str(image), classes=[0], verbose=False, conf=0.25)
    except Exception:
        return []
    if not res:
        return []
    im = cv2.imread(str(image))
    if im is None:
        return []
    h, w = im.shape[:2]
    boxes = []
    for r in res:
        if r.boxes is None:
            continue
        for b in r.boxes:
            xyxy = b.xyxy[0].tolist()
            conf = float(b.conf[0]) if b.conf is not None else 0.0
            area = max(0.0, (xyxy[2] - xyxy[0]) * (xyxy[3] - xyxy[1]))
            boxes.append((area, conf, xyxy))
    boxes.sort(key=lambda t: (t[0], t[1]), reverse=True)
    saved: list[Path] = []
    for i, (_, _, xyxy) in enumerate(boxes[:max_crops]):
        x1, y1, x2, y2 = [int(round(v)) for v in xyxy]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)
        if x2 - x1 < 16 or y2 - y1 < 16:
            continue
        crop = im[y1:y2, x1:x2]
        dest = out_dir / f"{stem}_p{i}.jpg"
        if cv2.imwrite(str(dest), crop) and dest.is_file() and dest.stat().st_size > 200:
            saved.append(dest)
    if not saved:
        # Whole-frame fallback so every still contributes
        dest = out_dir / f"{stem}_full.jpg"
        try:
            shutil.copy2(image, dest)
        except Exception:
            return saved
        if dest.is_file() and dest.stat().st_size > 200:
            saved.append(dest)
    return saved


def export_yolo_cls_dataset(
    *,
    on_status: OnStatus = None,
    val_fraction: float = 0.2,
    seed: int = 42,
) -> dict[str, Any]:
    from clip_ft import dataset_dir
    from config import OUTPUT_DIR

    # Prefer deep CLIP dataset if present; else export shallow stills first
    root = dataset_dir()
    keep_src = sorted((root / "keep").glob("*.jpg")) if (root / "keep").is_dir() else []
    pass_src = sorted((root / "pass").glob("*.jpg")) if (root / "pass").is_dir() else []
    if len(keep_src) < 8 or len(pass_src) < 3:
        from clip_ft import export_keep_pass_dataset_deep

        if on_status:
            on_status("CLIP dataset thin — deep-exporting Keep/Pass first…")
        exp = export_keep_pass_dataset_deep(on_status=on_status)
        if not exp.get("ok"):
            return {"ok": False, "error": "clip_export_failed", **exp}
        keep_src = sorted((root / "keep").glob("*.jpg"))
        pass_src = sorted((root / "pass").glob("*.jpg"))

    out = yolo_ft_dir()
    if out.exists():
        shutil.rmtree(out)
    rng = random.Random(seed)

    def split(paths: list[Path]) -> tuple[list[Path], list[Path]]:
        xs = list(paths)
        rng.shuffle(xs)
        if len(xs) <= 1:
            return xs, []
        n_val = max(1, int(round(len(xs) * val_fraction)))
        n_val = min(n_val, len(xs) - 1)
        return xs[n_val:], xs[:n_val]

    counts = {"train_keep": 0, "train_pass": 0, "val_keep": 0, "val_pass": 0}
    for label, paths in (("keep", keep_src), ("pass", pass_src)):
        tr, va = split(paths)
        for split_name, subset in (("train", tr), ("val", va)):
            dest_dir = out / split_name / label
            dest_dir.mkdir(parents=True, exist_ok=True)
            for src in subset:
                crops = _person_crops(src, dest_dir, stem=src.stem, max_crops=2)
                if not crops:
                    dest = dest_dir / src.name
                    shutil.copy2(src, dest)
                    crops = [dest]
                counts[f"{split_name}_{label}"] += len(crops)

    yaml_path = out / "data.yaml"
    # Ultralytics classify uses the folder itself as data=
    meta = {
        "ok": True,
        "path": str(out),
        "data": str(out),
        "counts": counts,
        "created_at": time.time(),
        "train_cmd": (
            f"yolo classify train model=yolov8s-cls.pt data={out.as_posix()} "
            f"epochs=40 imgsz=224 project={(OUTPUT_DIR / 'yolo_ft').as_posix()} name=cls"
        ),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    yaml_path.write_text(
        f"# classification dataset root\npath: {out.as_posix()}\n",
        encoding="utf-8",
    )
    if on_status:
        on_status(
            f"YOLO cls dataset · train keep={counts['train_keep']} pass={counts['train_pass']} "
            f"val keep={counts['val_keep']} pass={counts['val_pass']}"
        )
    return meta


def main() -> None:
    def status(msg: str) -> None:
        print(msg, flush=True)

    result = export_yolo_cls_dataset(on_status=status)
    print(json.dumps(result, indent=2, default=str))
    if not result.get("ok"):
        raise SystemExit(1)
    print("\nTrain on a CUDA machine / RunPod:")
    print(" ", result.get("train_cmd"))


if __name__ == "__main__":
    main()
