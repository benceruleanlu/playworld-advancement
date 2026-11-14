"""Summarise a cycle-RL run: training curves and held-out evaluation, base (step 0) vs later.

    python -m rl.report runs/rl/<run>            # writes <run>/report.md (+ PNGs if matplotlib is installed)

Reads config.json, metrics.jsonl and eval.jsonl written by rl.train. Every number in the
report comes from those files; nothing is re-scored here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []


def fmt(x, nd=4):
    return "-" if x is None else f"{x:.{nd}f}"


def main(run_dir: str):
    d = Path(run_dir)
    cfg = json.loads((d / "config.json").read_text()) if (d / "config.json").exists() else {}
    steps = read_jsonl(d / "metrics.jsonl")
    evals = read_jsonl(d / "eval.jsonl")
    lines = [f"# Cycle RL run `{d.name}`", ""]
    if cfg:
        keys = ("world", "steps", "group_size", "groups_per_rank", "n_chunks", "train_chunks", "lr", "beta",
                "lora_rank", "yaw_min", "yaw_max", "curriculum", "seed")
        lines += ["Config: " + ", ".join(f"{k}={cfg[k]}" for k in keys if k in cfg), ""]

    if evals:
        lines += ["## Held-out evaluation (fixed images, cycles, seeds)", "",
                  "| step | reward | memory | local | local_min | sharp | ctrl err (deg) | closure err (deg) |",
                  "|---|---|---|---|---|---|---|---|"]
        lines += [f"| {e['step']} | {fmt(e.get('reward'))} | {fmt(e.get('memory'))} | {fmt(e.get('local'))} | "
                  f"{fmt(e.get('local_min'))} | {fmt(e.get('sharp'))} | {fmt(e.get('ctrl_err_deg'), 2)} | "
                  f"{fmt(e.get('closure_err_deg'), 2)} |" for e in evals]
        base, last = evals[0], evals[-1]
        if len(evals) > 1:
            lines += ["", f"Change from step {base['step']} to step {last['step']}: "
                      + ", ".join(f"{k} {last[k] - base[k]:+.4f}" for k in ("reward", "memory", "local", "sharp", "ctrl_err_deg", "closure_err_deg")
                                  if base.get(k) is not None and last.get(k) is not None)]
        bins = list(base.get("gap_curve", {}))
        if bins:
            lines += ["", "### Consistency vs time gap (frames between the two views of a pair)", "",
                      "| step | " + " | ".join(bins) + " |", "|---|" + "---|" * len(bins)]
            lines += [f"| {e['step']} | " + " | ".join(fmt(e.get("gap_curve", {}).get(b)) for b in bins) + " |"
                      for e in evals]
        kinds = sorted(k for k in base if k.startswith("memory_eval"))
        if kinds:
            lines += ["", "### Memory by probe cycle", "", "| step | " + " | ".join(kinds) + " |",
                      "|---|" + "---|" * len(kinds)]
            lines += [f"| {e['step']} | " + " | ".join(fmt(e.get(k)) for k in kinds) + " |" for e in evals]

    if steps:
        lines += ["", "## Training (on-policy rollouts)", "",
                  "| step | reward | in-group std | memory | local | sharp | grad norm | s/step |",
                  "|---|---|---|---|---|---|---|---|"]
        lines += [f"| {s['step']} | {fmt(s.get('reward_mean'))} | {fmt(s.get('reward_std'))} | {fmt(s.get('memory'))} | "
                  f"{fmt(s.get('local'))} | {fmt(s.get('sharp'))} | {fmt(s.get('grad_norm'), 3)} | {s['seconds']:.0f} |"
                  for s in steps]
        lines += ["", "Final curriculum weights: " + json.dumps(steps[-1].get("curriculum", {}))]

    try:
        import matplotlib  # noqa: PLC0415
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: PLC0415
        if steps:
            fig, ax = plt.subplots(figsize=(7, 3.5))
            for k in ("memory", "local", "sharp"):
                ax.plot([s["step"] for s in steps], [s.get(k) for s in steps], label=k)
            ax.set_xlabel("step"), ax.set_ylabel("train reward term"), ax.legend(), fig.tight_layout()
            fig.savefig(d / "train_curves.png", dpi=120)
            lines += ["", "![training curves](train_curves.png)"]
        if evals and evals[0].get("gap_curve"):
            fig, ax = plt.subplots(figsize=(7, 3.5))
            for e in (evals[0], evals[-1]):
                g = e["gap_curve"]
                ax.plot(list(g), list(g.values()), marker="o", label=f"step {e['step']}")
            ax.set_xlabel("frame gap"), ax.set_ylabel("pair consistency"), ax.legend(), fig.tight_layout()
            fig.savefig(d / "gap_curve.png", dpi=120)
            lines += ["", "![consistency vs gap](gap_curve.png)"]
    except ImportError:
        pass
    (d / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])
