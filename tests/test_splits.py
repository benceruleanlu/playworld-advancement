"""Split invariants: dev unchanged, dev2 disjoint from dev, dev + dev2 + heldout = all, and the script reproduces the files."""
import importlib.util
import shutil
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / "splits"
FAMILIES = ("gc", "if", "insight", "outsight")
# dev.tsv as committed on 2026-11-14; dev2 must never change it
DEV = ("GC005 GC016 GC031 GC033 GC036 GC038 IF002 IF010 IF017 IF031 IF034 IF052 "
       "OE001 OE005 OE018 OE035 OE064 OE074 OE034 OE039 OE047 OE048 OE058 OE069").split()


def rows(name):
    return [tuple(l.split("\t")) for l in (SPLITS / f"{name}.tsv").read_text().splitlines() if l.strip()]


def test_split_sizes_and_partition():
    dev, dev2, dev48, held, all_ = (rows(n) for n in ("dev", "dev2", "dev48", "heldout", "all"))
    assert (len(dev), len(dev2), len(dev48), len(held), len(all_)) == (24, 24, 48, 123, 171)
    for split in (dev, dev2):
        assert Counter(f for f, _ in split) == {f: 6 for f in FAMILIES}
    assert dev48 == dev + dev2
    ids = [{t for _, t in s} for s in (dev, dev2, held)]
    assert not (ids[0] & ids[1]) and not (ids[0] & ids[2]) and not (ids[1] & ids[2])
    assert set(dev + dev2 + held) == set(all_) and len(set(all_)) == 171


def test_dev_unchanged():
    assert [t for _, t in rows("dev")] == DEV


@pytest.mark.skipif(not all((ROOT / "data" / f / "data.json").is_file() for f in FAMILIES), reason="needs dataset JSON")
def test_script_reproduces_files(tmp_path):
    (tmp_path / "splits").mkdir()
    for f in FAMILIES:
        (tmp_path / "data" / f).mkdir(parents=True)
        shutil.copy(ROOT / "data" / f / "data.json", tmp_path / "data" / f / "data.json")
    spec = importlib.util.spec_from_file_location("make_splits", SPLITS / "make_splits.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOT = tmp_path
    assert mod.main() == 0
    for name in ("dev", "dev2", "dev48", "heldout", "all"):
        assert (tmp_path / "splits" / f"{name}.tsv").read_bytes() == (SPLITS / f"{name}.tsv").read_bytes(), name
