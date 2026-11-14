"""Cycle-consistency RL for LingBot-World v2 1.3B on Modal (rl/ package).

    modal run modal_rl.py::prep                                   # COCO train/eval + PlayWorld GC dev eval images
    modal run modal_rl.py --run rl-smoke --gpus 1 --steps 2 --group-size 2 --eval-images 2 --n-chunks 4
    modal run --detach modal_rl.py --run rl-v1 --gpus 8 --steps 40
    modal volume get pwa-rl runs/rl-v1 runs/rl                     # metrics.jsonl, eval.jsonl, LoRA, videos

Weights come from the `pwa-weights` Volume (prefetch_lingbot.py --variant 1.3b layout); data,
logs, checkpoints and videos go to the `pwa-rl` Volume. No secrets are needed.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import modal

from adapters.lingbot_world2.modal_image import FLASH_ATTN, LINGBOT_REF

ROOT = Path(__file__).resolve().parent
app = modal.App("pwa-cycle-rl")
weights_vol = modal.Volume.from_name("pwa-weights", create_if_missing=True)
rl_vol = modal.Volume.from_name("pwa-rl", create_if_missing=True)

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.11")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0", "wget", "unzip")
    .pip_install("torch==2.5.1", "torchvision==0.20.1", "torchaudio==2.5.1",
                 index_url="https://download.pytorch.org/whl/cu124")
    .pip_install(
        "opencv-python-headless>=4.9.0.80", "diffusers>=0.31.0", "transformers>=4.49.0,<=4.51.3",
        "tokenizers>=0.20.3", "accelerate>=1.1.1", "tqdm", "imageio[ffmpeg]", "easydict", "ftfy",
        "imageio-ffmpeg", "numpy>=1.23.5,<2", "scipy", "einops", "safetensors", FLASH_ATTN,
        "httpx", "Pillow", "peft==0.17.1", "huggingface_hub")
    .run_commands(f"git clone https://github.com/Robbyant/lingbot-world-v2 /opt/lingbot "
                  f"&& cd /opt/lingbot && git checkout {LINGBOT_REF}")
    .env({"LINGBOT_ROOT": "/opt/lingbot", "LINGBOT_WEIGHTS": "/weights/lingbot", "PYTHONPATH": "/repo",
          "RL_VOLUME": "pwa-rl", "TOKENIZERS_PARALLELISM": "false"})
    .add_local_dir(ROOT, "/repo", ignore=[".git", ".venv", "runs", "results", "site", "data",
                                          "**/__pycache__", "*.egg-info", "third_party"])
)


def _crop(src, dst, w=832, h=480):
    """Center-crop to the generation aspect (832:480) and resize."""
    from PIL import Image  # noqa: PLC0415
    img = Image.open(src).convert("RGB")
    W, H = img.size
    ar = w / h
    if W / H > ar:
        nw = int(H * ar)
        img = img.crop(((W - nw) // 2, 0, (W - nw) // 2 + nw, H))
    else:
        nh = int(W / ar)
        img = img.crop((0, (H - nh) // 2, W, (H - nh) // 2 + nh))
    img.resize((w, h), Image.LANCZOS).save(dst, quality=95)


@app.function(image=image, volumes={"/rl": rl_vol}, timeout=3600, cpu=8, memory=16384)
def prep(n_train: int = 3000, n_eval: int = 64, seed: int = 0):
    """COCO val2017 (Flickr photos, CC BY) -> /rl/data/{train,eval}; PlayWorld GC dev -> /rl/data/pw_gc_dev.
    PlayWorld images are for evaluation only; they never enter training."""
    import json  # noqa: PLC0415
    import random  # noqa: PLC0415
    import zipfile  # noqa: PLC0415

    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    tmp = Path("/tmp/coco")
    tmp.mkdir(parents=True, exist_ok=True)
    for url in ("http://images.cocodataset.org/zips/val2017.zip",
                "http://images.cocodataset.org/annotations/annotations_trainval2017.zip"):
        dst = tmp / url.rsplit("/", 1)[1]
        subprocess.run(["wget", "-q", "-O", str(dst), url], check=True)
        zipfile.ZipFile(dst).extractall(tmp)
    ann = json.loads((tmp / "annotations" / "captions_val2017.json").read_text())
    caps = {}
    for a in ann["annotations"]:
        caps.setdefault(a["image_id"], a["caption"].strip())
    imgs = [im for im in ann["images"] if im["width"] >= 600 and im["height"] >= 400 and im["id"] in caps]
    random.Random(seed).shuffle(imgs)
    splits = {"eval": imgs[:n_eval], "train": imgs[n_eval:n_eval + n_train]}
    for split, rows in splits.items():
        d = Path("/rl/data") / split
        d.mkdir(parents=True, exist_ok=True)
        out = {}
        for im in rows:
            name = f"coco_{im['id']:012d}.jpg"
            _crop(tmp / "val2017" / im["file_name"], d / name)
            out[name] = caps[im["id"]]
        (d / "captions.json").write_text(json.dumps(out, indent=1))
        print(f"{split}: {len(out)} images")

    dev = [l.strip().split("\t") for l in Path("/repo/splits/dev.tsv").read_text().splitlines() if l.startswith("gc\t")]
    gc = json.load(open(hf_hub_download("jocelynd/playworld-bench", "gc/data.json", repo_type="dataset")))
    recs = {r["task_id"]: r for r in gc}
    d = Path("/rl/data/pw_gc_dev")
    d.mkdir(parents=True, exist_ok=True)
    out = {}
    for _, tid in dev:
        r = recs[tid.strip()]
        src = hf_hub_download("jocelynd/playworld-bench", r["image_path"], repo_type="dataset")
        _crop(src, d / f"{tid.strip()}.jpg")
        out[f"{tid.strip()}.jpg"] = r["image_caption"]
    (d / "captions.json").write_text(json.dumps(out, indent=1))
    print(f"pw_gc_dev: {len(out)} images")
    rl_vol.commit()


@app.function(image=image, gpu="H100", timeout=24 * 3600, memory=65536,
              volumes={"/weights": weights_vol, "/rl": rl_vol})
def train(argv: list[str], gpus: int = 1) -> int:
    cmd = ["torchrun", f"--nproc_per_node={gpus}", "--master_port=29511", "-m", "rl.train", *argv]
    print("$", " ".join(cmd), flush=True)
    try:
        return subprocess.run(cmd, cwd="/repo", env={**os.environ}).returncode
    finally:
        rl_vol.commit()


@app.local_entrypoint()
def main(run: str, gpus: int = 1, steps: int = 40, group_size: int = 8, groups_per_rank: int = 1,
         n_chunks: int = 8, eval_images: int = 16, eval_every: int = 10, lr: float = 5e-5, extra: str = ""):
    import re  # noqa: PLC0415
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run):
        raise SystemExit(f"bad run name {run!r}")
    existing = {Path(e.path).name for e in rl_vol.listdir("runs")} if _has_runs() else set()
    if run in existing:
        raise SystemExit(f"run {run} already exists in pwa-rl:/runs; pick a new name")
    argv = ["--exp", run, "--steps", str(steps), "--group-size", str(group_size),
            "--groups-per-rank", str(groups_per_rank), "--n-chunks", str(n_chunks),
            "--eval-images", str(eval_images), "--eval-every", str(eval_every), "--lr", str(lr),
            "--git-sha", _git_sha(), *extra.split()]
    # each rank holds T5 + DiT on the host while loading (~25 GB)
    rc = train.with_options(gpu=f"H100:{gpus}", memory=32768 * gpus).remote(argv, gpus)
    print(f"train exit code {rc}")
    if rc:
        raise SystemExit(rc)


def _git_sha() -> str:
    def git(*a):
        r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    sha = git("rev-parse", "--short", "HEAD") or "unknown"
    return sha + ("-dirty" if git("status", "--porcelain", "--", "rl", "modal_rl.py", "adapters") else "")


def _has_runs() -> bool:
    try:
        return any(True for _ in rl_vol.listdir("runs"))
    except Exception:  # noqa: BLE001 - no runs dir yet
        return False
