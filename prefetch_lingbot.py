"""Download LingBot-World v2 causal-fast weights into the shared Modal cache (CPU only).

    modal run prefetch_lingbot.py --variant 14b     # 86 GB
    modal run prefetch_lingbot.py --variant 1.3b    # 7 GB DiT + 12 GB shared T5/VAE/tokenizer from the 14B repo
"""

import os

import modal

app = modal.App("playworld-lingbot-prefetch")
# Public weights need no secret; HF_TOKEN is passed from the launching environment when it is set, so this
# runs in any Modal workspace without a `pwa` secret (the workflows still create that for the generation apps).
HF_SECRET = [modal.Secret.from_dict({"HF_TOKEN": os.environ["HF_TOKEN"]})] if os.environ.get("HF_TOKEN") else []
weights = modal.Volume.from_name("pwa-weights", create_if_missing=True)
image = modal.Image.debian_slim(python_version="3.11").pip_install("huggingface_hub", "hf_xet")
ROOT = "/weights/lingbot"
R14 = "lingbot-world-v2-14b-causal-fast"
R13 = "lingbot-world-v2-1.3b-causal-fast"


@app.function(image=image, volumes={"/weights": weights}, secrets=HF_SECRET,
              timeout=3 * 3600, cpu=4)
def prefetch(variant: str = "14b"):
    from huggingface_hub import snapshot_download

    if variant == "1.3b":
        # The 1.3B repo ships DiT shards only; the loader looks for them under transformers/.
        jobs = [(R14, f"{ROOT}/{R14}", None, ["transformers/*"]),
                (R13, f"{ROOT}/{R13}/transformers", None, None)]
    else:
        jobs = [(R14, f"{ROOT}/{R14}", None, None)]
    for repo, dest, allow, ignore in jobs:
        print(f"Prefetching robbyant/{repo} -> {dest}", flush=True)
        snapshot_download(f"robbyant/{repo}", local_dir=dest, allow_patterns=allow, ignore_patterns=ignore)
        weights.commit()
        print(f"Cached {repo}", flush=True)


@app.local_entrypoint()
def main(variant: str = "14b"):
    prefetch.remote(variant)
