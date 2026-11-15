"""Drive the live LingBot kernel on Modal (editor_app.py) from this machine: `python -m pwa.kernel ...`.

The agent or person asking the questions runs here; LingBot stays loaded on a Modal GPU. `exec` sends
one Python cell, prints its output, saves any images the cell sent back under
outputs/editor/, and appends the cell and its result to outputs/editor/log.jsonl
(the record of what was asked and seen). Stdlib only; `modal` is imported on use.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .core import ROOT, PwaError

# PWA_EDITOR_APP names another deployment of the same app (set it for `modal deploy` and for the client), e.g. to
# keep a 1.3B and a 14B kernel side by side or to bring up changed code without stopping a running batch.
APP, CLS = os.environ.get("PWA_EDITOR_APP") or "pwa-editor", "Kernel"
HINT = ("Is the kernel deployed (`modal deploy editor_app.py`) and is this machine logged in to Modal "
        "(`modal token new`, or MODAL_TOKEN_ID / MODAL_TOKEN_SECRET in config/env.sh)?")


def out_dir() -> Path:
    return Path(os.environ.get("PWA_EDITOR_OUT") or ROOT / "outputs" / "editor")


def read_code(file: str | None, code: str | None, stdin=None) -> str:
    if code is not None and file not in (None, "-"):
        raise PwaError("give the cell as FILE or as -c CODE, not both", 2)
    if code is None:
        if file in (None, "-"):
            code = (stdin or sys.stdin).read()
        else:
            path = Path(file)
            if not path.is_file():
                raise PwaError(f"no such file: {file}", 2)
            code = path.read_text()
    if not code.strip():
        raise PwaError("empty cell", 2)
    return code


def connect():
    try:
        import modal  # noqa: PLC0415
    except ImportError:
        raise PwaError("the kernel client needs the Modal SDK: pip install modal") from None
    return modal.Cls.from_name(APP, CLS)()


def call(kernel, method: str, *args):
    try:
        return getattr(kernel, method).remote(*args)
    except PwaError:
        raise
    except Exception as e:  # noqa: BLE001 - not deployed, not logged in, container crash
        raise PwaError(f"kernel call failed: {type(e).__name__}: {str(e)[:500]}\n{HINT}") from None


def safe_name(name: str) -> str:
    """Artifact names come from code that ran remotely: keep a plain file name."""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(str(name)).name).lstrip(".")
    return name or "artifact"


def save_artifacts(artifacts: list[dict], dest: Path, stamp: str) -> list[Path]:
    paths = []
    for i, art in enumerate(artifacts or []):
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{stamp}_{i:02d}_{safe_name(art.get('name', ''))}"
        path.write_bytes(art["data"])
        paths.append(path)
    return paths


def run_cell(kernel, code: str, dest: Path | None = None, now: datetime | None = None) -> dict:
    """Send one cell, save its images, log it. Returns the result with local artifact paths."""
    dest = dest or out_dir()
    now = now or datetime.now(timezone.utc)
    res = call(kernel, "run", code)
    paths = save_artifacts(res.pop("artifacts", []), dest, now.strftime("%Y%m%dT%H%M%S%f")[:-3])
    res["artifacts"] = [str(p) for p in paths]
    dest.mkdir(parents=True, exist_ok=True)
    with (dest / "log.jsonl").open("a") as f:
        f.write(json.dumps({"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "code": code, **res}, ensure_ascii=False) + "\n")
    return res


def render(res: dict) -> str:
    parts = [res.get("stdout") or ""]
    if res.get("error"):
        parts.append(res["error"])
    parts += [f"[image] {p}" for p in res.get("artifacts", [])]
    st = res.get("status") or {}
    parts.append(f"[kernel] {'ok' if res.get('ok') else 'ERROR'} in {res.get('seconds')}s; "
                 f"passes {st.get('passes')}, probes {st.get('probes')}")
    return "\n".join(p.rstrip("\n") for p in parts if p)


def cli(argv: list[str] | None = None) -> int:
    """`python -m pwa.kernel exec [FILE | -c CODE] | status | reset [--json]` (the same as `pwa kernel ...`)."""
    import argparse  # noqa: PLC0415

    from .core import load_env  # noqa: PLC0415
    ap = argparse.ArgumentParser(prog="python -m pwa.kernel", description=__doc__)
    ap.add_argument("action", choices=["exec", "status", "reset"])
    ap.add_argument("file", nargs="?", help="exec: file holding the cell ('-' or omitted reads stdin)")
    ap.add_argument("-c", dest="code", metavar="CODE", help="exec: the cell as a string")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    load_env()
    try:
        return main(a)
    except PwaError as e:
        print(f"pwa kernel: {e}", file=sys.stderr)
        return e.code


def main(a) -> int:
    kernel = connect()
    if a.action == "exec":
        res = run_cell(kernel, read_code(a.file, a.code))
        print(json.dumps(res, indent=2, ensure_ascii=False) if a.json else render(res))
        return 0 if res.get("ok") else 1
    st = call(kernel, "reset" if a.action == "reset" else "status")
    print(json.dumps(st, indent=2) if a.json else "\n".join(f"{k:<14} {v}" for k, v in st.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
