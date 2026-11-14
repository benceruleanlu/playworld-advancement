"""Turn-away / turn-back probe for LingBot's memory (GPU; step 0-1 of the memory study).

For each task image and trajectory: settle, yaw right by ANGLE, hold, yaw back,
settle. Steps are fed to a LingBotSession in closed-loop sized pieces (28 keys,
then 32), so the computation matches a persistent closed-loop rollout. The probe
then pairs every frame on the way back with the frame on the way out at the same
yaw and records whether the outbound latent was still in the KV cache when the
return frame was generated (cache_model.visible). If similarity collapses exactly
when the outbound latents are evicted, the memory problem is cache policy, not
attention weights.

    LINGBOT_VARIANT=1.3b python -m adapters.lingbot_world2.probe probe-v1 \\
        --tasks OE034 OE039 --angles 45 90 180 --holds 0 48 --windows=18:6,36:6,-1:0

On Modal: PWA_RUNNER=lingbot_world2_1p3b modal run modal_app.py::probe --exp probe-v1 ...
Writes runs/EXP/probe/<task>/<traj>.mp4 and .json, and runs/EXP/probe/summary.{json,tsv}.
Similarity is PSNR and pixel correlation on 112x64 frames, plus DINOv2 cosine with --dino.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.lingbot_world2 import cache_model as C  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402
from adapters.lingbot_world2 import session as S  # noqa: E402

SETTLE_IN, SETTLE_OUT = 12, 32
FIRST_KEYS = S.keys_needed(2, first=True)   # 28, as the closed-loop harness
NEXT_KEYS = S.keys_needed(2, first=False)   # 32


# ------------------------------------------------------------ pure logic

def trajectory(angle_deg: float, hold: int, rate_deg: float) -> list[str]:
    """Per-frame keys: settle, 'l' for angle, hold, 'j' back, settle; padded to whole steps."""
    n = max(1, round(angle_deg / rate_deg))
    keys = ["none"] * SETTLE_IN + ["l"] * n + ["none"] * hold + ["j"] * n + ["none"] * SETTLE_OUT
    extra = (len(keys) - FIRST_KEYS) % NEXT_KEYS
    return keys + ["none"] * ((NEXT_KEYS - extra) % NEXT_KEYS)


def split_steps(keys: list[str]) -> list[list[str]]:
    steps = [keys[:FIRST_KEYS]]
    for i in range(FIRST_KEYS, len(keys), NEXT_KEYS):
        steps.append(keys[i:i + NEXT_KEYS])
    return steps


def yaws(keys: list[str], rate_deg: float) -> np.ndarray:
    """Yaw in degrees for every pixel frame (frame 0 = input image)."""
    d = np.array([rate_deg if k == "l" else -rate_deg if k == "j" else 0.0 for k in keys])
    return np.concatenate([[0.0], np.cumsum(d)])


def phases(keys: list[str]) -> dict[str, list[int]]:
    """Pixel-frame indices of the outbound turn, hold and return turn."""
    first_l = keys.index("l") + 1
    last_l = len(keys) - keys[::-1].index("l")
    first_j = keys.index("j") + 1
    last_j = len(keys) - keys[::-1].index("j")
    return {"pre": list(range(0, first_l)), "out": list(range(first_l, last_l + 1)),
            "back": list(range(first_j, last_j + 1)), "post": list(range(last_j + 1, len(keys) + 1))}


def latent_of(frame: int) -> int:
    """Pixel frame -> the latent that produced it (latent 0 = frame 0, then 4 frames each)."""
    return 0 if frame == 0 else (frame - 1) // 4 + 1


def pairs(keys: list[str], rate_deg: float, local: int, sink: int, tol: float | None = None) -> list[dict]:
    """Each return-turn frame paired with the outbound frame of the nearest yaw (and each
    post-settle frame with the last pre-turn frame); in_cache = that outbound latent was
    attended to while the return frame's chunk was generated."""
    y = yaws(keys, rate_deg)
    ph = phases(keys)
    tol = rate_deg / 2 + 1e-6 if tol is None else tol
    out = []
    ref = ph["pre"][-1]
    for kind, frames, cands in (("turn", ph["back"], ph["out"] + ph["pre"]), ("settle", ph["post"], [ref])):
        cands = np.array(cands)
        for f in frames:
            j = int(cands[np.argmin(np.abs(y[cands] - y[f]))])
            if abs(y[j] - y[f]) > tol:
                continue
            lf, lj = latent_of(f), latent_of(j)
            c = lf // C.CHUNK  # the chunk's own keys are attended to as well
            vis = set(C.visible(c, local, sink)) | set(range(c * C.CHUNK, (c + 1) * C.CHUNK))
            out.append({"kind": kind, "frame": f, "ref": j, "yaw": round(float(y[f]), 2),
                        "gap_latents": lf - lj, "in_cache": lj in vis, "ref_in_sink": lj < sink})
    return out


def _small(fr: np.ndarray, size=(112, 64)) -> np.ndarray:
    from PIL import Image  # noqa: PLC0415
    return np.asarray(Image.fromarray(fr).resize(size, Image.BILINEAR), dtype=np.float32) / 255.0


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a - b) ** 2))
    return 99.0 if mse <= 1e-10 else 10 * math.log10(1.0 / mse)


def corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a.ravel() - a.mean()
    b = b.ravel() - b.mean()
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def aggregate(rows: list[dict]) -> dict:
    """Mean metrics split by kind and by whether the reference latent was in the cache."""
    out = {}
    for kind in ("turn", "settle"):
        for cached in (True, False):
            sel = [r for r in rows if r["kind"] == kind and r["in_cache"] == cached]
            key = f"{kind}_{'cached' if cached else 'evicted'}"
            out[key + "_n"] = len(sel)
            for m in ("psnr", "corr", "dino"):
                vals = [r[m] for r in sel if r.get(m) is not None]
                out[f"{key}_{m}"] = round(float(np.mean(vals)), 4) if vals else None
    return out


# ------------------------------------------------------------- GPU side

class Dino:
    def __init__(self):
        import torch  # noqa: PLC0415
        self.torch = torch
        self.m = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14").cuda().eval()

    def embed(self, frames: np.ndarray) -> np.ndarray:
        t = self.torch
        x = t.from_numpy(frames).permute(0, 3, 1, 2).float().div(255).cuda()
        x = t.nn.functional.interpolate(x, size=(224, 392), mode="bilinear", align_corners=False)
        mean = t.tensor([0.485, 0.456, 0.406], device=x.device).view(1, 3, 1, 1)
        std = t.tensor([0.229, 0.224, 0.225], device=x.device).view(1, 3, 1, 1)
        with t.no_grad():
            e = self.m((x - mean) / std)
        return t.nn.functional.normalize(e, dim=-1).cpu().numpy()


def run_one(session, image, prompt, seed, keys, rate_deg, dino=None):
    P.YAW = math.radians(rate_deg)
    session.reset(image, prompt, seed, horizon_frames=len(keys) + 1)
    frames = []
    for i, step in enumerate(split_steps(keys)):
        fr = session.step(step)
        frames.append(fr if i == 0 else fr[1:])
    video = np.concatenate(frames)
    assert len(video) == len(keys) + 1, (len(video), len(keys))
    local, sink = session.pipe.local_attn_size, session.pipe.sink_size
    rows = pairs(keys, rate_deg, local, sink)
    small = {}
    emb = dino.embed(video) if dino else None
    for r in rows:
        for f in (r["frame"], r["ref"]):
            if f not in small:
                small[f] = _small(video[f])
        r["psnr"] = round(psnr(small[r["frame"]], small[r["ref"]]), 3)
        r["corr"] = round(corr(small[r["frame"]], small[r["ref"]]), 4)
        r["dino"] = round(float(emb[r["frame"]] @ emb[r["ref"]]), 4) if emb is not None else None
    return video, rows, session.cache_report()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("exp")
    ap.add_argument("--tasks", nargs="+", default=["OE034", "OE039", "OE047"])
    ap.add_argument("--angles", nargs="+", type=float, default=[45, 90, 180])
    ap.add_argument("--holds", nargs="+", type=int, default=[0, 48])
    ap.add_argument("--windows", default="18:6",
                    help="comma-separated local_attn:sink; write --windows=18:6,-1:0 (argparse rejects a bare -1:0)")
    ap.add_argument("--rate", type=float, default=45 / 32, help="yaw degrees per pixel frame (turn-cal chunk rate)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fps", type=int, default=16)
    ap.add_argument("--dino", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args(argv)

    import imageio  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    from adapters.lingbot_world2 import loader as L  # noqa: PLC0415
    from pwa import core  # noqa: PLC0415

    root = core.RUNS / args.exp / "probe"
    if root.exists() and not args.resume:
        raise SystemExit(f"{root} exists; pick a new experiment name or pass --resume")
    root.mkdir(parents=True, exist_ok=True)
    windows = [tuple(int(x) for x in w.split(":")) for w in args.windows.split(",") if w.strip()]
    pipe, cfg, variant = L.load_pipe(*windows[0])
    dino = Dino() if args.dino else None
    summary = []
    for tid in args.tasks:
        fam = core.family_of(tid)
        info, rec = core.task_info(fam, tid), core.records(fam)[tid]
        image = Image.open(info["image"]).convert("RGB")
        prompt = rec.get("prompt") or "A photo-realistic scene with rich details."
        for local, sink in windows:
            L.set_window(pipe, local, sink)
            session = S.LingBotSession(pipe, L.MAX_AREA, cfg.sample_shift)
            for angle in args.angles:
                for hold in args.holds:
                    name = f"yaw{angle:g}_hold{hold}_w{local}s{sink}"
                    out = root / tid / f"{name}.json"
                    if out.exists():
                        summary.append(json.loads(out.read_text())["summary"])
                        continue
                    keys = trajectory(angle, hold, args.rate)
                    t0 = time.time()
                    video, rows, cache = run_one(session, image, prompt, args.seed, keys, args.rate, dino)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    imageio.mimsave(str(out.with_suffix(".mp4")), list(video), fps=args.fps)
                    summ = {"task": tid, "family": fam, "variant": variant, "angle": angle, "hold": hold,
                            "local_attn": local, "sink": sink, "frames": len(video),
                            "secs": round(time.time() - t0, 1), **aggregate(rows)}
                    out.write_text(json.dumps({"summary": summ, "keys": keys, "pairs": rows, "cache": cache}))
                    summary.append(summ)
                    print(f"[probe] {tid} {name}: " + " ".join(
                        f"{k}={v}" for k, v in summ.items() if k.endswith(("_psnr", "_dino", "_n")) and v is not None),
                        flush=True)
    (root / "summary.json").write_text(json.dumps(summary, indent=1))
    if summary:
        cols = list(summary[0])
        lines = ["\t".join(cols)] + ["\t".join("" if s.get(c) is None else str(s.get(c)) for c in cols) for s in summary]
        (root / "summary.tsv").write_text("\n".join(lines) + "\n")
    print(f"[probe] wrote {root}/summary.tsv ({len(summary)} rollouts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
