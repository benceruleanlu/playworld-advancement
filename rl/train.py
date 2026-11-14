"""Self-verifiable cycle RL for LingBot-World v2 1.3B (torchrun entry point).

    torchrun --nproc_per_node=N -m rl.train --run NAME [--steps 40 --group-size 8 ...]

Every rank loads the model, rolls out its own groups (one training image and one closed
rotation cycle per group, G seeds), scores each rollout with rl.rewards.cycle_reward,
normalises rewards within the group, and accumulates NFT gradients (rl.policy). Gradients
are all-reduced and every rank takes the same AdamW step, so LoRA weights stay identical.

Rank 0 writes <out>/<run>/: config.json, metrics.jsonl (one line per step), eval.jsonl (held-out
images, fixed cycles and seeds; step 0 is the released model), lora_step<N>.safetensors and
sample videos. The cycle mix adapts to the policy's own results: kinds with lower memory reward
are sampled more (logged as curriculum weights).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

import numpy as np

from rl.cycles import Cycle, frame_rotations, full_turn, n_keys_for, out_and_back, sample_cycle
from rl.rewards import RewardConfig, cycle_reward, gap_curve

KINDS = ("out_back", "out_back_hold", "repeat", "full_turn", "pitch_back")


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--exp", required=True, help="run name (not --run: torchrun takes that as --run-path)")
    p.add_argument("--out", default="/rl/runs")
    p.add_argument("--data", default="/rl/data")
    p.add_argument("--steps", type=int, default=40)
    p.add_argument("--groups-per-rank", type=int, default=1)
    p.add_argument("--group-size", type=int, default=8)
    p.add_argument("--n-chunks", type=int, default=8, help="latent chunks per rollout (frames = 16n-3)")
    p.add_argument("--train-chunks", type=int, default=3, help="chunks per rollout that get gradients")
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--beta", type=float, default=1.0)
    p.add_argument("--lora-rank", type=int, default=16)
    p.add_argument("--grad-clip", type=float, default=1.0)
    p.add_argument("--yaw-min", type=float, default=0.02)
    p.add_argument("--yaw-max", type=float, default=0.04)
    p.add_argument("--eval-every", type=int, default=10)
    p.add_argument("--eval-images", type=int, default=16)
    p.add_argument("--save-every", type=int, default=5)
    p.add_argument("--curriculum", type=int, default=1)
    p.add_argument("--pw-eval", type=int, default=1, help="also evaluate on the PlayWorld GC dev images")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--init-lora", default="", help="resume from a LoRA safetensors file")
    p.add_argument("--git-sha", default="", help="code version (set by modal_rl.py)")
    return p.parse_args(argv)


# ---------------------------------------------------------------- data

def load_items(data: Path, split: str) -> list[dict]:
    caps = json.loads((data / split / "captions.json").read_text())
    return [{"path": str(data / split / f), "prompt": c, "name": Path(f).stem} for f, c in sorted(caps.items())]


def eval_cycles(n_chunks: int) -> list[Cycle]:
    """Fixed held-out probes: a 96-degree out-and-back, two 48-degree round trips, ~1.1 full turns."""
    yaw = 0.03
    return [
        Cycle("eval_out_back", out_and_back(n_chunks, 56, "l"), yaw, 0.01, {"out": 56}),
        Cycle("eval_repeat", out_and_back(n_chunks, 28, "j", repeats=2), yaw, 0.01, {"out": 28, "repeats": 2}),
        Cycle("eval_full_turn", full_turn(n_chunks, 0, "l"), 2.2 * math.pi / n_keys_for(n_chunks), 0.01, {}),
    ]


# ---------------------------------------------------------------- helpers

def group_r(rewards: np.ndarray) -> tuple[np.ndarray, float]:
    """Group-normalised advantage mapped to r in [0, 1] (0.5 = average)."""
    std = float(rewards.std())
    if std < 1e-4:
        return np.full(len(rewards), 0.5), std
    a = (rewards - rewards.mean()) / std
    return np.clip(0.5 + 0.25 * a, 0.0, 1.0), std


def save_video(frames: np.ndarray, path: Path, fps: int = 16):
    import imageio  # noqa: PLC0415
    path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(str(path), list(frames), fps=fps, quality=7)


def commit_volume():
    try:
        import modal  # noqa: PLC0415
        modal.Volume.from_name(os.environ.get("RL_VOLUME", "pwa-rl")).commit()
    except Exception as e:  # noqa: BLE001 - outside Modal or no volume: nothing to commit
        print(f"[rl] volume commit skipped: {e}", flush=True)


def jsonl(path: Path, obj: dict):
    with path.open("a") as f:
        f.write(json.dumps(obj) + "\n")


# ---------------------------------------------------------------- main

def main(argv=None):
    import torch  # noqa: PLC0415
    import torch.distributed as dist  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    from safetensors.torch import load_file, save_file  # noqa: PLC0415

    from rl.policy import CyclePolicy, add_lora, load_lora_state, load_pipe, lora_state  # noqa: PLC0415

    args = parse_args(argv)
    dist.init_process_group("nccl")
    rank, world = dist.get_rank(), dist.get_world_size()
    torch.cuda.set_device(int(os.environ.get("LOCAL_RANK", 0)))
    out = Path(args.out) / args.exp
    if rank == 0:
        out.mkdir(parents=True, exist_ok=True)
        (out / "config.json").write_text(json.dumps({**vars(args), "world": world}, indent=2))

    t0 = time.time()
    pipe, cfg = load_pipe()
    lora = add_lora(pipe.model, rank=args.lora_rank, alpha=args.lora_rank)
    if args.init_lora:
        load_lora_state(lora, load_file(args.init_lora))
    for p in lora.values():  # identical start on every rank (LoRA A is randomly initialised)
        dist.broadcast(p.data, 0)
    policy = CyclePolicy(pipe, cfg, lora)
    opt = torch.optim.AdamW(list(lora.values()), lr=args.lr, weight_decay=0.0)
    print(f"[rl] rank {rank}/{world} ready in {time.time() - t0:.0f}s, "
          f"{sum(p.numel() for p in lora.values()) / 1e6:.2f}M LoRA params", flush=True)

    data = Path(args.data)
    train_items = load_items(data, "train")
    eval_items = load_items(data, "eval")[: args.eval_images]
    if args.pw_eval and (data / "pw_gc_dev").exists():
        eval_items += [{**it, "name": "pw_" + it["name"]} for it in load_items(data, "pw_gc_dev")]
    rcfg = RewardConfig()
    curr = {k: 0.5 for k in KINDS}  # EMA of memory reward per kind

    def evaluate(step: int):
        cyc = eval_cycles(args.n_chunks)
        jobs = [(it, c) for it in eval_items for c in cyc]
        mine = jobs[rank::world]
        rows = []
        for j, (it, c) in enumerate(mine):
            img = Image.open(it["path"]).convert("RGB")
            ro = policy.rollout(img, it["prompt"], c.keys, 1234, c.yaw_rad, c.pitch_rad)
            rots = frame_rotations(c)
            r = cycle_reward(ro["frames"], rots, rcfg)
            g = gap_curve(ro["frames"], rots, rcfg)
            rows.append({"item": it["name"], "cycle": c.kind, **r, "gap": g})
            if rank == 0 and j < 2:
                save_video(ro["frames"], out / "videos" / f"eval_step{step:03d}_{it['name']}_{c.kind}.mp4")
        allrows = [None] * world
        dist.all_gather_object(allrows, rows)
        if rank == 0:
            flat = [r for rr in allrows for r in rr]
            summ = {"step": step, "n": len(flat), "time": time.time() - t0}
            for key in ("reward", "local", "local_min", "memory", "sharp", "ctrl", "ctrl_err_deg", "closure_err_deg"):
                vals = [r[key] for r in flat if r[key] is not None and np.isfinite(r[key])]
                summ[key] = float(np.mean(vals)) if vals else None
            for kind in {r["cycle"] for r in flat}:
                vals = [r["memory"] for r in flat if r["cycle"] == kind and np.isfinite(r["memory"])]
                summ[f"memory_{kind}"] = float(np.mean(vals)) if vals else None
            bins = flat[0]["gap"].keys() if flat else []
            summ["gap_curve"] = {b: float(np.mean([r["gap"][b][0] for r in flat if r["gap"][b][0] is not None]))
                                 for b in bins if any(r["gap"][b][0] is not None for r in flat)}
            jsonl(out / "eval.jsonl", summ)
            jsonl(out / "eval_rows.jsonl", {"step": step, "rows": flat})
            print(f"[rl] eval step {step}: reward {summ['reward']:.4f} memory {summ['memory']} "
                  f"local {summ['local']:.4f} sharp {summ['sharp']:.4f} ctrl_err {summ['ctrl_err_deg']} deg "
                  f"closure_err {summ['closure_err_deg']} deg", flush=True)
            commit_volume()
        dist.barrier()

    evaluate(0)
    for step in range(1, args.steps + 1):
        ts = time.time()
        rng = np.random.default_rng(args.seed * 1_000_003 + step * 1009 + rank)
        kinds = list(KINDS)
        if args.curriculum:
            w = np.array([1.0 - curr[k] + 0.1 for k in kinds])
            probs = w / w.sum()
        else:
            probs = np.full(len(kinds), 1 / len(kinds))
        opt.zero_grad(set_to_none=True)
        groups, t_roll, t_train = [], 0.0, 0.0
        for g in range(args.groups_per_rank):
            it = train_items[int(rng.integers(len(train_items)))]
            kind = str(rng.choice(kinds, p=probs))
            cyc = sample_cycle(rng, args.n_chunks, (args.yaw_min, args.yaw_max), kinds=(kind,))
            rots = frame_rotations(cyc)
            img = Image.open(it["path"]).convert("RGB")
            seeds = [int(rng.integers(2 ** 31)) for _ in range(args.group_size)]
            outs, rews = [], []
            tr = time.time()
            for sd in seeds:
                ro = policy.rollout(img, it["prompt"], cyc.keys, sd, cyc.yaw_rad, cyc.pitch_rad)
                rew = cycle_reward(ro["frames"], rots, rcfg)
                outs.append(ro["latents"])
                rews.append(rew)
                if rank == 0 and g == 0 and sd == seeds[0] and step % args.save_every == 0:
                    save_video(ro["frames"], out / "videos" / f"train_step{step:03d}_{it['name']}_{cyc.kind}.mp4")
            t_roll += time.time() - tr
            R = np.array([r["reward"] for r in rews])
            rr, gstd = group_r(R)
            tt = time.time()
            losses = []
            if gstd >= 1e-4:
                n_c = args.n_chunks
                for lat, sd, r in zip(outs, seeds, rr):
                    chunks = sorted(rng.choice(np.arange(1, n_c), size=min(args.train_chunks, n_c - 1), replace=False))
                    losses.append(policy.accumulate_grad(
                        img, it["prompt"], cyc.keys, sd, cyc.yaw_rad, cyc.pitch_rad, lat, float(r),
                        [int(c) for c in chunks], beta=args.beta,
                        weight=1.0 / (args.group_size * args.groups_per_rank * world)))
            t_train += time.time() - tt
            groups.append({"item": it["name"], "kind": cyc.kind, "params": cyc.params, "yaw": cyc.yaw_rad,
                           "reward_mean": float(R.mean()), "reward_std": gstd,
                           "memory": float(np.nanmean([r["memory"] for r in rews])),
                           "local": float(np.mean([r["local"] for r in rews])),
                           "local_min": float(np.mean([r["local_min"] for r in rews])),
                           "sharp": float(np.mean([r["sharp"] for r in rews])),
                           "ctrl_err_deg": float(np.nanmean([np.nan if r["ctrl_err_deg"] is None else r["ctrl_err_deg"] for r in rews])),
                           "loss": float(np.mean(losses)) if losses else None})

        for p in lora.values():  # sum of per-rank (already 1/world-weighted) gradients
            if p.grad is None:
                p.grad = torch.zeros_like(p)
            dist.all_reduce(p.grad)
        gnorm = float(torch.nn.utils.clip_grad_norm_(list(lora.values()), args.grad_clip))
        opt.step()

        allg = [None] * world
        dist.all_gather_object(allg, groups)
        flat = [g for gg in allg for g in gg]
        for k in KINDS:  # curriculum update, identical on every rank
            mem = [g["memory"] for g in flat if g["kind"] == k and np.isfinite(g["memory"])]
            if mem:
                curr[k] = 0.8 * curr[k] + 0.2 * float(np.mean(mem))
        if rank == 0:
            row = {"step": step, "seconds": time.time() - ts, "rollout_s": t_roll, "train_s": t_train,
                   "grad_norm": gnorm, "lr": args.lr,
                   "curriculum": {k: round(float(p), 3) for k, p in zip(kinds, probs)}, "memory_ema": curr}
            for key in ("reward_mean", "reward_std", "memory", "local", "local_min", "sharp", "ctrl_err_deg"):
                vals = [g[key] for g in flat if g[key] is not None and np.isfinite(g[key])]
                row[key] = float(np.mean(vals)) if vals else None
            row["groups"] = flat
            jsonl(out / "metrics.jsonl", row)
            print(f"[rl] step {step}: reward {row['reward_mean']:.4f} (in-group std {row['reward_std']:.4f}) "
                  f"memory {row['memory']} local {row['local']:.4f} sharp {row['sharp']:.4f} ctrl_err {row['ctrl_err_deg']} "
                  f"gnorm {gnorm:.3g} {row['seconds']:.0f}s", flush=True)
            if step % args.save_every == 0 or step == args.steps:
                save_file(lora_state(lora), str(out / f"lora_step{step:03d}.safetensors"))
                commit_volume()
        if step % args.eval_every == 0 or step == args.steps:
            evaluate(step)
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
