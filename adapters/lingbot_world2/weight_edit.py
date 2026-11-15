"""Gradient-free weight edits for the LingBot DiT (weight-space programming).

An edit is a list of additive deltas on named DiT parameters, kept in one .npz
file: numpy arrays plus a JSON manifest, loaded with allow_pickle=False. Ops:

  dense    a delta with the parameter's own shape
  lowrank  a [out, r] @ b [r, rest], reshaped to the parameter (a rank-r update,
           e.g. removing one direction from what a Linear writes)
  sparse   values added at flat indices

Edits only add, so they compose: `--lingbot-edit a,b` applies a then b and the
result is the sum of the deltas. The manifest records each touched parameter's
shape and norm at the time the edit was made, so applying it to another
checkpoint, in another order, or twice fails instead of silently doing
something else.

The released DiT weights are bfloat16 (8 significant bits). A weight moves only
when its delta is at least about 0.2% of its own magnitude; anything smaller
rounds away. apply() reports how many weights really changed and `survival`,
the norm of the change that landed over the norm that was asked for.

Everything except fingerprint/apply/revert/apply_spec/detach_model is numpy-only and
unit-tested (tests/test_weight_edit.py); torch is imported lazily.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

FORMAT = 1
MANIFEST = "__manifest__"
KINDS = {"dense": ("delta",), "lowrank": ("a", "b"), "sparse": ("idx", "val")}
EDIT_FLAG = "--lingbot-edit"
EDITS_DIR = "/weights/edits"
BASE_RTOL = 1e-4
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class EditError(Exception):
    """A weight edit that cannot be built, loaded or applied as asked."""


def check_name(name: str) -> str:
    if not _NAME.match(name or ""):
        raise EditError(f"bad edit name {name!r}: use letters, digits, '.', '_' or '-' (max 80)")
    return name


def _np(x, dtype) -> np.ndarray:
    """numpy array from a list, array or torch tensor (bfloat16 goes through float32)."""
    if hasattr(x, "detach"):
        x = x.detach().cpu()
        x = (x.float() if x.is_floating_point() else x).numpy()
    return np.ascontiguousarray(np.asarray(x), dtype=dtype)


class WeightEdit:
    def __init__(self, name: str, variant: str = "", notes: str = "", parents=()):
        self.name = check_name(name)
        self.variant = variant        # "1.3b" | "14b" | "" (unchecked)
        self.notes = notes
        self.parents = list(parents)  # edits that were applied when this one was made
        self.created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.ops: list[dict] = []     # {"param", "kind", "arrays": {key: ndarray}}
        self.base: dict[str, dict] = {}  # param -> {"shape", "norm"} before this edit
        self.extra: dict = {}         # free-form: probe budget, scores, rationale

    # -- building ----------------------------------------------------------
    def _add(self, param: str, kind: str, **arrays) -> "WeightEdit":
        if not param or not isinstance(param, str):
            raise EditError(f"parameter name must be a non-empty string, got {param!r}")
        for key, arr in arrays.items():
            if arr.dtype.kind == "f" and not np.isfinite(arr).all():
                raise EditError(f"{kind} op on {param}: {key} has NaN or inf")
        self.ops.append({"param": param, "kind": kind, "arrays": arrays})
        return self

    def dense(self, param: str, delta) -> "WeightEdit":
        return self._add(param, "dense", delta=_np(delta, np.float32))

    def lowrank(self, param: str, a, b) -> "WeightEdit":
        a, b = _np(a, np.float32), _np(b, np.float32)
        if a.ndim == 1:
            a = a[:, None]
        if b.ndim == 1:
            b = b[None, :]
        if a.ndim != 2 or b.ndim < 2 or a.shape[1] != b.shape[0]:
            raise EditError(f"lowrank op on {param}: want a [out, r] and b [r, ...], got {a.shape} and {b.shape}")
        return self._add(param, "lowrank", a=a, b=b)

    def sparse(self, param: str, idx, val) -> "WeightEdit":
        idx, val = _np(idx, np.int64).reshape(-1), _np(val, np.float32).reshape(-1)
        if idx.shape != val.shape:
            raise EditError(f"sparse op on {param}: {idx.size} indices but {val.size} values")
        if idx.size and idx.min() < 0:
            raise EditError(f"sparse op on {param}: negative flat index")
        return self._add(param, "sparse", idx=idx, val=val)

    # -- reading -----------------------------------------------------------
    def params(self) -> list[str]:
        return list(dict.fromkeys(op["param"] for op in self.ops))

    def delta_for(self, param: str, shape) -> np.ndarray:
        """float32 sum of this edit's ops on `param`, in the parameter's shape."""
        shape = tuple(int(s) for s in shape)
        size = int(np.prod(shape, dtype=np.int64))
        out = np.zeros(shape, dtype=np.float32)
        for op in self.ops:
            if op["param"] != param:
                continue
            arr, kind = op["arrays"], op["kind"]
            if kind == "dense":
                if arr["delta"].shape != shape:
                    raise EditError(f"dense op on {param}: delta is {arr['delta'].shape}, parameter is {shape}")
                out += arr["delta"]
            elif kind == "lowrank":
                a, b = arr["a"], arr["b"].reshape(arr["b"].shape[0], -1)
                if a.shape[0] * b.shape[1] != size or a.shape[0] != shape[0]:
                    raise EditError(f"lowrank op on {param}: {a.shape} @ {b.shape} does not fill {shape}")
                out += (a @ b).reshape(shape)
            else:
                if arr["idx"].size and arr["idx"].max() >= size:
                    raise EditError(f"sparse op on {param}: index {int(arr['idx'].max())} outside {size} weights")
                np.add.at(out.reshape(-1), arr["idx"], arr["val"])
        return out

    # -- file --------------------------------------------------------------
    def manifest(self) -> dict:
        return {"format": FORMAT, "name": self.name, "variant": self.variant, "notes": self.notes,
                "parents": self.parents, "created": self.created, "base": self.base, "extra": self.extra,
                "ops": [{"param": op["param"], "kind": op["kind"]} for op in self.ops]}

    def save(self, path) -> str:
        """Write the edit to `path` (atomic). Returns the file's sha256."""
        if not self.ops:
            raise EditError(f"edit {self.name} has no ops")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {f"{i}.{key}": arr for i, op in enumerate(self.ops) for key, arr in op["arrays"].items()}
        arrays[MANIFEST] = np.array(json.dumps(self.manifest(), sort_keys=True))
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with tmp.open("wb") as f:
            np.savez_compressed(f, **arrays)
        os.replace(tmp, path)
        return file_sha256(path)

    @classmethod
    def load(cls, path) -> "WeightEdit":
        path = Path(path)
        try:
            with np.load(path, allow_pickle=False) as z:
                data = {k: z[k] for k in z.files}
        except Exception as e:  # truncated upload, wrong file type, pickled payload
            raise EditError(f"cannot read edit file {path}: {e}") from None
        if MANIFEST not in data:
            raise EditError(f"{path} is not a weight edit (no manifest)")
        m = json.loads(str(data[MANIFEST]))
        if m.get("format") != FORMAT:
            raise EditError(f"{path}: edit format {m.get('format')!r}, this code reads {FORMAT}")
        edit = cls(m["name"], m.get("variant", ""), m.get("notes", ""), m.get("parents", ()))
        edit.created = m.get("created", edit.created)
        edit.base, edit.extra = m.get("base", {}), m.get("extra", {})
        for i, op in enumerate(m["ops"]):
            if op["kind"] not in KINDS:
                raise EditError(f"{path}: unknown op kind {op['kind']!r}")
            try:
                arrays = {key: data[f"{i}.{key}"] for key in KINDS[op["kind"]]}
            except KeyError as e:
                raise EditError(f"{path}: op {i} is missing array {e}") from None
            getattr(edit, op["kind"])(op["param"], **arrays)
        return edit


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------ naming a spec

def pop_flag(argv: list[str], flag: str = EDIT_FLAG) -> tuple[list[str], str]:
    """Strip `--lingbot-edit SPEC` / `--lingbot-edit=SPEC` from argv -> (rest, spec)."""
    rest, spec, i = [], [], 0
    while i < len(argv):
        a = argv[i]
        if a == flag:
            if i + 1 >= len(argv):
                raise EditError(f"{flag} needs a value (edit name or path, comma-separated to stack)")
            spec.append(argv[i + 1])
            i += 2
        elif a.startswith(flag + "="):
            spec.append(a[len(flag) + 1:])
            i += 1
        else:
            rest.append(a)
            i += 1
    return rest, ",".join(spec)


def split_spec(spec: str) -> list[str]:
    return [s.strip() for s in (spec or "").split(",") if s.strip()]


def resolve(item: str, edits_dir=EDITS_DIR) -> Path:
    """An existing file path as given, else <edits_dir>/<name>.npz."""
    p = Path(item)
    if p.is_file():
        return p
    q = Path(edits_dir) / f"{item}.npz"
    if q.is_file():
        return q
    have = sorted(f.stem for f in Path(edits_dir).glob("*.npz")) if Path(edits_dir).is_dir() else []
    raise EditError(f"no weight edit {item!r} (looked for {p} and {q}); saved edits: {', '.join(have) or 'none'}")


# ------------------------------------------------------------------- torch

def fingerprint(model, names) -> dict[str, dict]:
    params = dict(model.named_parameters())
    return {n: {"shape": list(params[n].shape), "norm": float(params[n].detach().float().norm())} for n in names}


def apply(model, edit: WeightEdit, *, variant: str = "", check_base: bool = True, backup: dict | None = None) -> dict:
    """Add the edit to `model` in place and return what landed.

    `backup` (optional dict) receives the pre-edit tensor of every parameter it
    does not hold yet, so a workspace can revert. Fingerprints missing from the
    edit are recorded from the weights as they are now. Nothing is changed when
    any check fails."""
    import torch  # noqa: PLC0415

    if edit.variant and variant and edit.variant != variant:
        raise EditError(f"edit {edit.name} is for LingBot {edit.variant}, the loaded model is {variant}")
    params = dict(model.named_parameters())
    names = edit.params()
    missing = [n for n in names if n not in params]
    if missing:
        raise EditError(f"edit {edit.name}: no such parameter(s) {missing[:5]}; see names with model.named_parameters()")
    now = fingerprint(model, names)
    deltas = {}
    for n in names:
        deltas[n] = edit.delta_for(n, params[n].shape)  # shape errors surface before any write
        want = edit.base.get(n)
        if want is None:
            continue
        if list(want["shape"]) != now[n]["shape"]:
            raise EditError(f"edit {edit.name}: {n} is {now[n]['shape']}, the edit was made for {want['shape']}")
        if check_base and abs(now[n]["norm"] - want["norm"]) > BASE_RTOL * max(abs(want["norm"]), 1e-12):
            raise EditError(
                f"edit {edit.name}: {n} has norm {now[n]['norm']:.6g}, the edit was made against {want['norm']:.6g}. "
                f"Wrong checkpoint, wrong stacking order (parents: {edit.parents or 'none'}), or already applied.")
    for n in names:
        edit.base.setdefault(n, now[n])

    per, req_sq, eff_sq, requested, changed = {}, 0.0, 0.0, 0, 0
    with torch.no_grad():
        for n in names:
            p = params[n]
            if backup is not None and n not in backup:
                backup[n] = p.detach().clone()
            delta = torch.from_numpy(deltas[n]).to(p.device)
            old = p.detach().float()
            new = (old + delta).to(p.dtype)
            landed = new.float() - old
            stats = {"requested": int((delta != 0).sum()), "changed": int((landed != 0).sum()),
                     "requested_norm": float(delta.norm()), "effective_norm": float(landed.norm()),
                     "base_norm": now[n]["norm"]}
            p.copy_(new)
            per[n] = stats
            req_sq += stats["requested_norm"] ** 2
            eff_sq += stats["effective_norm"] ** 2
            requested += stats["requested"]
            changed += stats["changed"]
    total = sum(p.numel() for p in model.parameters())
    return {"name": edit.name, "params": per, "requested": requested, "changed": changed, "model_params": total,
            "fraction": changed / total if total else 0.0,
            "survival": (eff_sq ** 0.5) / (req_sq ** 0.5) if req_sq else 0.0}


def revert(model, backup: dict) -> int:
    """Restore every parameter held in `backup` and empty it. Returns how many."""
    import torch  # noqa: PLC0415
    params = dict(model.named_parameters())
    with torch.no_grad():
        for n, old in backup.items():
            params[n].copy_(old)
    n = len(backup)
    backup.clear()
    return n


def summary(stats: dict) -> str:
    return (f"{stats['name']}: changed {stats['changed']:,} of {stats['model_params']:,} weights "
            f"({100 * stats['fraction']:.4f}%) in {len(stats['params'])} parameter(s), "
            f"survival {stats['survival']:.2f}")


def detach_model(model) -> int:
    """Undo everything apply_spec put on `model`: back to the weights it was loaded with.
    The runner calls it before each arm, because arms in one process share the loaded pipe.
    Returns how many parameters were restored."""
    if model is None:
        return 0
    backup = getattr(model, "_pwa_edit_backup", None)
    n = revert(model, backup) if backup else 0
    for attr in ("_pwa_edit_backup", "_pwa_weight_edits"):
        if attr in getattr(model, "__dict__", {}):
            delattr(model, attr)
    return n


def apply_spec(model, spec: str, edits_dir=EDITS_DIR, variant: str = "") -> list[dict]:
    """Runner path: apply every edit named in `spec`, in order, or raise EditError.
    An edit that changes no weight is an error: the run would be the stock model
    under an edited name. The pre-edit weights are kept on the model for detach_model()."""
    if "_pwa_weight_edits" not in model.__dict__:
        model._pwa_weight_edits, model._pwa_edit_backup = [], {}
    seen, backup = model._pwa_weight_edits, model._pwa_edit_backup
    out = []
    for item in split_spec(spec):
        path = resolve(item, edits_dir)
        sha = file_sha256(path)
        if sha in seen:
            raise EditError(f"edit {item} ({sha[:12]}) is already applied to this model")
        edit = WeightEdit.load(path)
        stats = apply(model, edit, variant=variant, backup=backup)
        if not stats["changed"]:
            raise EditError(f"edit {edit.name} changed no weights (deltas below bfloat16 resolution?)")
        seen.append(sha)
        out.append({**stats, "path": str(path), "sha256": sha, "notes": edit.notes, "parents": edit.parents})
    return out
