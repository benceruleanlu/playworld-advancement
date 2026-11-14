#!/usr/bin/env python3
"""Write deterministic dev / heldout / all task splits from data/*/data.json.

dev: 6 tasks per family (gc, if, insight, outsight), seeded. Iterate on these.
heldout: everything else. Only score it at the final full run.
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("gc", "if", "insight", "outsight")
PER_FAMILY = 6
SEED = 20261114


def main() -> int:
    rng = random.Random(SEED)
    dev, heldout, all_ids = [], [], []
    for fam in FAMILIES:
        path = ROOT / "data" / fam / "data.json"
        if not path.is_file():
            print(f"missing {path}; run setup.sh first", file=sys.stderr)
            return 1
        ids = sorted(t["task_id"] for t in json.loads(path.read_text()))
        picked = sorted(rng.sample(ids, PER_FAMILY))
        dev += [f"{fam}\t{i}" for i in picked]
        heldout += [f"{fam}\t{i}" for i in ids if i not in picked]
        all_ids += [f"{fam}\t{i}" for i in ids]
    for name, rows in (("dev", dev), ("heldout", heldout), ("all", all_ids)):
        (ROOT / "splits" / f"{name}.tsv").write_text("\n".join(rows) + "\n")
        print(f"{name}: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
