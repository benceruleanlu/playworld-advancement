"""GPU-side tools for the live LingBot kernel (editor_app.py).

The kernel keeps LingBot loaded on a Modal GPU and runs Python cells sent from another machine
(`python -m pwa.kernel exec`). State lives between cells. Each cell sees:

  ws      this Workspace: tasks, scripted camera trials, activation capture, images to send back
  pipe    the loaded wan.WanI2VCausal;  model = pipe.model (the DiT)
  torch, np, P (poses), S (session), CP (camera_probe), MT (measured_turn)

A typical sequence of cells:

    t = ws.task("GC033")                                       # dev tasks only
    frames, out = ws.turn_trial(t, [("j", 90), ("l", 90)])     # left 90, right 90, no player
    out["segments"], out["closure"]                            # rendered turn per leg, end view against frame 0
    frames, out = ws.servo_trial(t, [("j", 90), ("l", 90)])    # the same script under the yaw servo
    ws.show(frames)                                            # contact sheet comes back to the laptop

Trials are measurements of the model, not benchmark scores. A claim about a score still needs a run scored by
the official judge under the adoption rule (AGENTS.md).

Everything above the Workspace class is torch-free and unit-tested (tests/test_workspace.py).
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import math
import os
import re
import time
import traceback
from pathlib import Path

import numpy as np

from adapters.lingbot_world2 import camera_probe as CP
from adapters.lingbot_world2 import measured_turn as MT
from adapters.lingbot_world2 import poses as P
from adapters.lingbot_world2 import session as S
from adapters.lingbot_world2 import yaw_servo as YSV

MAX_STDOUT = 20_000            # characters of cell output sent back
MAX_ARTIFACT_BYTES = 24 << 20  # per cell
FAMILIES = ("gc", "if", "insight", "outsight")
MAX_AREA = 480 * 832  # run.MAX_AREA: the released checkpoints' reference resolution
DEFAULT_PROMPT = "A photo-realistic scene with rich details."  # run.DEFAULT_PROMPT
DATASET = "jocelynd/playworld-bench"


# ---------------------------------------------------------------- pure logic

def _clip(text: str, limit: int = MAX_STDOUT) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n... [{len(text) - limit} characters cut] ...\n{text[-half:]}"


def execute(ns: dict, code: str) -> dict:
    """Run `code` in `ns` like a notebook cell: output is captured and the value
    of a trailing expression is printed. Never raises; an exception (including
    SystemExit and KeyboardInterrupt) comes back as a traceback."""
    out = io.StringIO()
    err = None
    t0 = time.time()
    try:
        tree = ast.parse(code, "<cell>", "exec")
        last = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = ast.Expression(tree.body.pop().value)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            exec(compile(tree, "<cell>", "exec"), ns)  # noqa: S102 - the kernel's whole job
            if last is not None:
                value = eval(compile(last, "<cell>", "eval"), ns)  # noqa: S307
                if value is not None:
                    print(repr(value))
    except BaseException:  # noqa: BLE001 - a cell must not take the kernel down
        err = _clip(traceback.format_exc())
    return {"ok": err is None, "stdout": _clip(out.getvalue()), "error": err, "seconds": round(time.time() - t0, 2)}


def probe_chunks(n_keys: int) -> int:
    """Latent chunks a fresh rollout needs for n_keys per-frame keys (the first
    chunk takes 12, every later one 16)."""
    return max(1, math.ceil((int(n_keys) + 4) / S.FRAMES_PER_CHUNK))


def contact_sheet(frames: np.ndarray, n: int = 8, width: int = 320, cols: int = 4) -> np.ndarray:
    """n evenly spaced frames from uint8 [F, H, W, 3] as one image, each about `width` wide."""
    frames = np.asarray(frames)
    if frames.ndim != 4 or frames.shape[-1] != 3 or not len(frames):
        raise ValueError(f"want frames [F, H, W, 3], got {frames.shape}")
    n = max(1, min(int(n), len(frames)))
    pick = np.linspace(0, len(frames) - 1, n).round().astype(int)
    stride = max(1, frames.shape[2] // int(width))
    tiles = frames[pick][:, ::stride, ::stride]
    cols = min(cols, n)
    rows = math.ceil(n / cols)
    h, w = tiles.shape[1:3]
    sheet = np.zeros((rows * h, cols * w, 3), dtype=np.uint8)
    for i, tile in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet[r * h:(r + 1) * h, c * w:(c + 1) * w] = tile
    return sheet


def frame_stats(frames: np.ndarray) -> dict:
    """Cheap numbers for a rollout: how much consecutive frames differ, and how
    far the last frame is from the first (0-255 scale)."""
    f = np.asarray(frames, dtype=np.float32)
    step = np.abs(f[1:] - f[:-1]).mean(axis=(1, 2, 3)) if len(f) > 1 else np.zeros(1, dtype=np.float32)
    return {"frames": int(len(f)), "motion_mean": float(step.mean()), "motion_max": float(step.max()),
            "change_from_first": float(np.abs(f[-1] - f[0]).mean()), "brightness": float(f.mean())}


def find_task(data_root, task_id: str) -> tuple[str, dict]:
    """(family, record) for task_id from <data_root>/<family>/data.json."""
    for fam in FAMILIES:
        path = Path(data_root) / fam / "data.json"
        if path.is_file():
            for rec in json.loads(path.read_text()):
                if rec.get("task_id") == task_id:
                    return fam, rec
    raise KeyError(f"task {task_id!r} not found under {data_root}")


def dev_ids(repo) -> set[str]:
    """Task ids in splits/dev.tsv (family<TAB>task_id). Raises if the file is missing."""
    path = Path(repo) / "splits" / "dev.tsv"
    lines = [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    return {ln.split("\t")[1].strip() for ln in lines}


# ------------------------------------------------------------------ on GPU

class Workspace:
    def __init__(self, pipe, cfg, variant: str, *, repo="/repo",
                 data_dir="/weights/playworld-bench", commit=None, max_area: int = MAX_AREA):
        self.pipe, self.cfg, self.variant = pipe, cfg, variant
        self.model = pipe.model
        self.repo = Path(repo)
        self.data_dir = Path(data_dir)
        self._commit = commit or (lambda: None)  # persists the volume (dataset copy, trial files)
        self.session = S.LingBotSession(pipe, max_area, cfg.sample_shift)
        self.passes = 0      # DiT forward passes since the kernel started: the probe budget spent
        self.probes = 0
        self._artifacts: list[dict] = []
        self._started = time.time()
        self.n_params = sum(p.numel() for p in self.model.parameters())
        self.model.register_forward_hook(self._count)

    def _count(self, *_):
        self.passes += 1

    def namespace(self) -> dict:
        import torch  # noqa: PLC0415
        return {"ws": self, "pipe": self.pipe, "model": self.model, "torch": torch, "np": np,
                "P": P, "S": S, "CP": CP, "MT": MT, "YSV": YSV}

    def status(self) -> dict:
        import torch  # noqa: PLC0415
        vram = torch.cuda.max_memory_allocated() / 2 ** 30 if torch.cuda.is_available() else 0.0
        return {"variant": self.variant, "uptime_s": round(time.time() - self._started), "passes": self.passes,
                "probes": self.probes, "dit_params": self.n_params, "peak_vram_gib": round(vram, 1)}

    # -- looking -----------------------------------------------------------
    def params(self, pattern: str = "") -> list[tuple]:
        """[(name, shape, norm)] for DiT parameters whose name matches the regex."""
        rx = re.compile(pattern)
        return [(n, tuple(p.shape), round(float(p.detach().float().norm()), 4))
                for n, p in self.model.named_parameters() if rx.search(n)]

    def modules(self, pattern: str = "") -> list[str]:
        rx = re.compile(pattern)
        return [n for n, _ in self.model.named_modules() if n and rx.search(n)]

    def W(self, name: str):  # noqa: N802 - reads like the maths
        """The live parameter tensor (bfloat16 on the GPU). Read it; do not write to it."""
        params = dict(self.model.named_parameters())
        if name not in params:
            near = [n for n in params if name.split(".")[-1] in n][:8]
            raise KeyError(f"no parameter {name!r}; similar: {near}")
        return params[name]

    @contextlib.contextmanager
    def capture(self, names, fn=None):
        """Record module outputs while the block runs: {module: [one entry per DiT pass]}.
        `names` is a module name, a regex (full match) or a list of either. `fn(tensor)`
        reduces each entry; by default the detached tensor stays on the GPU, so keep
        the list of modules short or pass fn."""
        mods = dict(self.model.named_modules())
        want = [names] if isinstance(names, str) else list(names)
        picked = [n for n in mods if n and any(n == w or re.fullmatch(w, n) for w in want)]
        if not picked:
            raise KeyError(f"no module matches {want}; see ws.modules()")
        store = {n: [] for n in picked}

        def hook(name):
            def h(_mod, _args, out):
                t = out[0] if isinstance(out, (tuple, list)) else out
                store[name].append(fn(t) if fn else t.detach())
            return h

        handles = [mods[n].register_forward_hook(hook(n)) for n in picked]
        try:
            yield store
        finally:
            for h in handles:
                h.remove()

    # -- running -----------------------------------------------------------
    def _data_root(self) -> Path:
        # A checkout may hold only the task JSON (CI and tests download just that): need the images too,
        # the same test setup.sh uses.
        for root in (self.repo / "data", self.data_dir):
            if (root / "gc" / "data.json").is_file() and (root / "gc" / "images").is_dir():
                return root
        from huggingface_hub import snapshot_download  # noqa: PLC0415
        print(f"[workspace] downloading {DATASET} to {self.data_dir}", flush=True)
        snapshot_download(DATASET, repo_type="dataset", local_dir=str(self.data_dir))
        self._commit()
        return self.data_dir

    def task(self, task_id: str) -> dict:
        """A dev-split benchmark task: {"task_id", "family", "prompt", "image" (PIL), "record"}.
        Held-out tasks are refused so the final score stays clean (AGENTS.md)."""
        if task_id not in dev_ids(self.repo) and os.environ.get("PWA_EDITOR_ALLOW_HELDOUT") != "1":
            raise PermissionError(f"{task_id} is not in splits/dev.tsv; held-out tasks stay unseen until code freeze")
        from PIL import Image  # noqa: PLC0415
        root = self._data_root()
        fam, rec = find_task(root, task_id)
        return {"task_id": task_id, "family": fam, "prompt": rec.get("prompt", ""),
                "image": Image.open(root / rec["image_path"]).convert("RGB"), "record": rec}

    def probe(self, image, action, prompt: str | None = None, seed: int = 42) -> np.ndarray:
        """Short open-loop rollout under fixed actions -> uint8 frames [F, H, W, 3], input frame first.

        image: a ws.task() dict, a PIL image or a path. action: "w-28,j-32" (key-frames:
        w/s/a/d move, i/k/j/l look up/down/left/right, none waits, "w+j" combines) or a
        list with one key per frame. Rounded up to whole 16-frame chunks by repeating
        the last key. Costs 5 DiT passes per chunk (4 denoising steps and a cache write).
        Same image, action, prompt and seed give the same noise, so two probes differ
        only by the weights."""
        if isinstance(image, dict):
            prompt = image.get("prompt") if prompt is None else prompt
            image = image["image"]
        elif isinstance(image, (str, Path)):
            from PIL import Image  # noqa: PLC0415
            image = Image.open(image).convert("RGB")
        keys = P.parse_action(action) if isinstance(action, str) else list(action)
        n = probe_chunks(len(keys))
        keys = S.fit_keys(keys, S.keys_needed(n, first=True))
        self.session.reset(image, prompt or DEFAULT_PROMPT, int(seed),
                           horizon_frames=S.frames_returned(n, first=True))
        frames = self.session.step(keys)
        self.probes += 1
        return frames

    def turn_trial(self, task, segments, rate_deg: float = CP.RATE_DEG, yaw_gain=None, prompt: str = "caption",
                   seed: int = 42, setup=None) -> tuple[np.ndarray, dict]:
        """One scripted camera trial -> (frames, readout). See camera_probe.

        segments: [("l", degrees) | ("j", degrees) | ("none", frames)], right / left / wait, at rate_deg per
        frame (default: the dataset token rate, 22.5 degrees per 20 frames). yaw_gain: (left, right) as
        --lingbot-yaw-gain applies it to the poses the model gets. prompt: "caption" (the task's scene
        description, as --lingbot-caption-prompt), "goal" (the task's goal text) or any other string as is.
        setup(session) runs after the reset and before the step, for anything else a flag would set on the
        session or its pose track. The turn rate is restored afterwards."""
        import math  # noqa: PLC0415
        rec = task.get("record", {})
        text = {"caption": rec.get("image_caption") or DEFAULT_PROMPT, "goal": task.get("prompt") or DEFAULT_PROMPT}.get(prompt, prompt)
        keys, spans, n = CP.build(segments, rate_deg)
        old = P.YAW
        P.YAW = math.radians(rate_deg)
        try:
            self.session.reset(task["image"], text, int(seed), horizon_frames=S.frames_returned(n, first=True))
            self.session.track.yaw_gain = tuple(float(g) for g in yaw_gain) if yaw_gain else None
            if setup is not None:
                setup(self.session)
            frames = self.session.step(keys)
        finally:
            P.YAW = old
        self.probes += 1
        out = CP.summarize(frames, spans)
        out.update({"task": task.get("task_id"), "rate_deg": rate_deg, "yaw_gain": list(yaw_gain) if yaw_gain else None,
                    "prompt": prompt if prompt in ("caption", "goal") else "custom", "seed": int(seed), "chunks": n,
                    "script": [[k, a] for k, a in segments]})
        return frames, out

    def servo_trial(self, task, segments, rate_deg: float = CP.RATE_DEG, prompt: str = "caption", seed: int = 42,
                    rigid=YSV.rigid_share, **servo_kw) -> tuple[np.ndarray, dict]:
        """The same script as turn_trial under --lingbot-yaw-servo: the runner's own yaw_servo.step generates it
        chunk by chunk and sets each chunk's pose gain from the yaw the earlier chunks rendered. The readout adds
        the servo's estimates, its heading against the intended one, and one line per chunk."""
        import math  # noqa: PLC0415
        rec = task.get("record", {})
        text = {"caption": rec.get("image_caption") or DEFAULT_PROMPT, "goal": task.get("prompt") or DEFAULT_PROMPT}.get(prompt, prompt)
        keys, spans, n = CP.build(segments, rate_deg)
        servo, lines = YSV.YawServo(**servo_kw), []
        old = P.YAW
        P.YAW = math.radians(rate_deg)
        try:
            self.session.reset(task["image"], text, int(seed), horizon_frames=S.frames_returned(n, first=True))
            frames = YSV.step(self.session, servo, keys, rate_deg, MT.chunk_turn, rigid=rigid, log=lines.append)
        finally:
            P.YAW = old
        self.probes += 1
        out = CP.summarize(frames, spans)
        out.update({"task": task.get("task_id"), "rate_deg": rate_deg, "prompt": prompt if prompt in ("caption", "goal") else "custom",
                    "seed": int(seed), "chunks": n, "script": [[k, a] for k, a in segments],
                    "servo": {"adapt": True, "k": servo.k, "beta": servo.beta, "est": {k: round(v, 3) for k, v in servo.est.items()},
                              "heading": round(servo.heading, 2), "intended": round(servo.intended, 2),
                              "chunks": servo.chunks, "untrusted": servo.untrusted, "log": lines}})
        return frames, out

    # -- sending images back -----------------------------------------------
    def show(self, obj, name: str | None = None, video: bool = False) -> None:
        """Send an image back with this cell's result. Frames [F, H, W, 3] become a
        contact sheet (plus an mp4 with video=True); a PIL image or a file path is
        sent as is. The local client saves them under outputs/editor/."""
        from PIL import Image  # noqa: PLC0415
        idx = len(self._artifacts)

        def jpeg(img) -> bytes:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=85)
            return buf.getvalue()

        if isinstance(obj, (str, Path)):
            self._attach(name or Path(obj).name, Path(obj).read_bytes())
        elif isinstance(obj, Image.Image):
            self._attach(f"{name or f'image{idx}'}.jpg", jpeg(obj))
        else:
            frames = np.asarray(obj)
            if frames.ndim == 3:
                frames = frames[None]
            stem = name or f"probe{idx}"
            self._attach(f"{stem}.jpg", jpeg(Image.fromarray(contact_sheet(frames))))
            if video:
                import tempfile  # noqa: PLC0415

                import imageio  # noqa: PLC0415
                with tempfile.TemporaryDirectory() as d:
                    mp4 = Path(d) / "probe.mp4"
                    imageio.mimsave(str(mp4), list(frames), fps=16)
                    self._attach(f"{stem}.mp4", mp4.read_bytes())

    def _attach(self, name: str, data: bytes) -> None:
        if sum(len(a["data"]) for a in self._artifacts) + len(data) > MAX_ARTIFACT_BYTES:
            raise ValueError(f"more than {MAX_ARTIFACT_BYTES >> 20} MB of images in one cell; send fewer or smaller ones")
        self._artifacts.append({"name": name, "data": data})

    def drain(self) -> list[dict]:
        out, self._artifacts = self._artifacts, []
        return out
