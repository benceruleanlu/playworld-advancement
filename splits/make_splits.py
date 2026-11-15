#!/usr/bin/env python3
"""Write deterministic task splits from data/*/data.json.

dev: 6 tasks per family (gc, if, insight, outsight), seeded with SEED. Iterate on these.
dev2: 6 more per family, drawn at random with DEV2_SEED from the tasks not in dev. Added
  on 2026-11-15, before any heldout task was scored, because the judge moves a six-task
  family mean by about 0.5 on identical videos. Its own generator, so dev is unchanged.
dev48: dev + dev2.
heldout: everything else (123). Only score it at the final full run.
all: every task (171).
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("gc", "if", "insight", "outsight")
PER_FAMILY = 6
SEED = 20261114
DEV2_SEED = 20261115


def main() -> int:
    rng = random.Random(SEED)
    rng2 = random.Random(DEV2_SEED)
    dev, dev2, heldout, all_ids = [], [], [], []
    for fam in FAMILIES:
        path = ROOT / "data" / fam / "data.json"
        if not path.is_file():
            print(f"missing {path}; run setup.sh first", file=sys.stderr)
            return 1
        ids = sorted(t["task_id"] for t in json.loads(path.read_text()))
        picked = sorted(rng.sample(ids, PER_FAMILY))
        rest = [i for i in ids if i not in picked]
        picked2 = sorted(rng2.sample(rest, PER_FAMILY))
        dev += [f"{fam}\t{i}" for i in picked]
        dev2 += [f"{fam}\t{i}" for i in picked2]
        heldout += [f"{fam}\t{i}" for i in rest if i not in picked2]
        all_ids += [f"{fam}\t{i}" for i in ids]
    for name, rows in (("dev", dev), ("dev2", dev2), ("dev48", dev + dev2), ("heldout", heldout), ("all", all_ids)):
        (ROOT / "splits" / f"{name}.tsv").write_text("\n".join(rows) + "\n")
        print(f"{name}: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
