import json, sys, shutil
from pathlib import Path
sys.path.insert(0, "src")
from clip_ft import dataset_dir, train_linear_probe, clip_ft_dir

# Replace live dataset with snapshot for training
live = dataset_dir()
snap = Path("output/clip_ft/dataset_train")
backup = Path("output/clip_ft/dataset_live_backup")
if backup.exists():
    shutil.rmtree(backup)
if live.exists():
    live.rename(backup)
shutil.copytree(snap, live)
try:
    def status(m):
        print(m, flush=True)
    result = train_linear_probe(on_status=status, device="cpu")
    print(json.dumps({k:v for k,v in result.items() if k != "history"}, indent=2, default=str))
finally:
    # restore live export dataset if backup exists
    if live.exists():
        shutil.rmtree(live)
    if backup.exists():
        backup.rename(live)
