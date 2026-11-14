"""Download the default SANA-WM inference assets into the shared Modal cache."""

import modal

app = modal.App("playworld-sana-prefetch")
weights = modal.Volume.from_name("pwa-weights", create_if_missing=True)
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "huggingface_hub", "hf_xet"
)


@app.function(
    image=image,
    volumes={"/weights": weights},
    secrets=[modal.Secret.from_name("pwa")],
    timeout=1800,
    cpu=2,
)
def prefetch():
    from huggingface_hub import snapshot_download

    # Match the default repos used by the pinned SANA pipeline. Gemma also
    # publishes an unsharded copy; Transformers reads the indexed shards.
    repos = (
        (
            "Efficient-Large-Model/SANA-WM_bidirectional",
            ["config.yaml", "dit/sana_wm_1600m_720p.safetensors", "vae/*", "refiner/**"],
        ),
        ("Efficient-Large-Model/gemma-2-2b-it", ["*.json", "tokenizer.model", "model-*.safetensors"]),
        ("yyfz233/Pi3X", ["config.json", "model.safetensors"]),
    )
    for repo, patterns in repos:
        print(f"Prefetching {repo}", flush=True)
        snapshot_download(repo, allow_patterns=patterns, cache_dir="/weights/hf/hub")
        weights.commit()
        print(f"Cached {repo}", flush=True)


@app.local_entrypoint()
def main():
    prefetch.remote()
