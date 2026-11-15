"""English display copies of the judge's reasons.

The official verifier's prompts are in Chinese, so its reasons (summary_zh, failure_reason_zh) usually are too.
translate() turns a batch of reason strings into English with one Gemini call per batch, for display only: it runs
after scoring, never touches a score, and the original text stays authoritative (every output keeps it).

- Only the reason strings are sent, plus a fixed instruction. Strings with no letters outside Latin are skipped.
- Cache: a JSON file keyed by sha256 of the source text (runs/EXP/eval/translations.json), so reruns are free.
- Any error or a missing GEMINI_API_KEY returns no translation for the failed strings; it never raises.
- PWA_TRANSLATE_MODEL picks the model (default DEFAULT_MODEL); PWA_TRANSLATE=0 turns translation off.
Stdlib only (urllib), so it also runs where the verifier's dependencies are not installed.
"""
from __future__ import annotations

import hashlib
import json
import os
import unicodedata
import urllib.request
from pathlib import Path
from typing import Callable, Iterable

from .core import log

DEFAULT_MODEL = "gemini-4-hydrogen"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BATCH = 25  # strings per call; a bad reply loses at most one batch
PROMPT = ("Translate the \"text\" of each object in the JSON array below into plain English. They are a video "
          "judge's comments on generated video clips. Keep task ids, numbers and scores as they are. Return only a "
          "JSON array of objects {\"id\": <same id>, \"en\": <English>}, exactly one per input object.\n\n")

Client = Callable[[str, str], str]  # (model, prompt) -> response text


def key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def needs_translation(text: str) -> bool:
    """True when text has a letter outside Latin (e.g. Chinese). English and ASCII text is shown as is."""
    return bool(text) and any(ord(c) > 0x24F and unicodedata.category(c).startswith("L") for c in text)


def model() -> str:
    return os.environ.get("PWA_TRANSLATE_MODEL") or DEFAULT_MODEL


def enabled() -> bool:
    return os.environ.get("PWA_TRANSLATE", "1") != "0"


def gemini_client(api_key: str, timeout: float = 120) -> Client:
    """One generateContent call over HTTPS; the key goes in a header, never in the URL or a log line."""
    def call(model_id: str, prompt: str) -> str:
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
        req = urllib.request.Request(API_URL.format(model=model_id), data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    return call


def default_client() -> Client | None:
    k = os.environ.get("GEMINI_API_KEY", "")
    return gemini_client(k) if k and enabled() else None


def request(chunk: list[str]) -> str:
    """The prompt for one batch: each source string carries an id, so the reply is matched by id, not order."""
    return PROMPT + json.dumps([{"id": n, "text": t} for n, t in enumerate(chunk)], ensure_ascii=False)


def _parse(reply: str, n: int) -> list[str]:
    """English strings in input order. Raises unless the reply has exactly the ids 0..n-1, once each, so a
    reordered, merged or split reply never attaches one task's translation to another."""
    s = reply.strip()
    if s.startswith("```"):
        s = s.strip("`").removeprefix("json").strip()
    out = json.loads(s)
    if not isinstance(out, list) or not all(
            isinstance(o, dict) and type(o.get("id")) is int and isinstance(o.get("en"), str) for o in out):
        raise ValueError("expected a JSON array of {id, en} objects")
    ids = [o["id"] for o in out]
    if sorted(ids) != list(range(n)):
        raise ValueError(f"expected ids 0..{n - 1} once each")
    by_id = {o["id"]: o["en"].strip() for o in out}
    return [by_id[i] for i in range(n)]


def load_cache(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(path: Path, cache: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
        tmp.replace(path)
    except OSError as e:
        log(f"[pwa] translate: cache not written ({type(e).__name__})")


def translate(texts: Iterable[str], cache_path: Path | None = None, client: Client | None = None,
              model_id: str | None = None) -> dict[str, str]:
    """English text for each string that needs translation, as {source: english}. Strings that need none, or
    whose translation failed, are absent. Never raises."""
    want = list(dict.fromkeys(t for t in texts if isinstance(t, str) and needs_translation(t)))
    if not want:
        return {}
    cache = load_cache(cache_path)
    out = {t: cache[key(t)]["en"] for t in want if isinstance(cache.get(key(t)), dict) and cache[key(t)].get("en")}
    todo = [t for t in want if t not in out]
    if not todo:
        return out
    if client is None:
        client = default_client()
    if client is None:
        log(f"[pwa] translate: {len(todo)} reason(s) left untranslated (no GEMINI_API_KEY or PWA_TRANSLATE=0)")
        return out
    mid = model_id or model()
    added = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        try:
            en = _parse(client(mid, request(chunk)), len(chunk))
        except Exception as e:  # noqa: BLE001  (display only: any failure leaves the original text)
            log(f"[pwa] translate: {len(chunk)} reason(s) left untranslated ({type(e).__name__})")
            continue
        for src, dst in zip(chunk, en):
            if dst:
                out[src] = dst
                cache[key(src)] = {"en": dst, "model": mid}
                added += 1
    if added and cache_path:
        _save_cache(Path(cache_path), cache)
    if added:
        log(f"[pwa] translate: {added} reason(s) translated with {mid}")
    return out


def fill(rows: list[dict], cache_path: Path | None = None, client: Client | None = None,
         field: str = "reason") -> int:
    """Set row['reason_en'] for rows whose reason needs translation and has none yet; '' where none is known.
    Returns how many rows gained one."""
    pending = [r for r in rows if needs_translation(r.get(field) or "") and not r.get(field + "_en")]
    tr = translate([r[field] for r in pending], cache_path, client) if pending else {}
    n = 0
    for r in rows:
        if r.get(field + "_en"):
            continue
        r[field + "_en"] = tr.get(r.get(field) or "", "")
        n += bool(r[field + "_en"])
    return n


FIELDS = ("reason", "fail_reason")  # each gets an English copy in FIELD_en


def translate_media(media_dir: Path, exps: list[str] | None = None, client: Client | None = None,
                    cache_path: Path | None = None, stats: dict | None = None) -> dict:
    """Fill missing reason_en / fail_reason_en fields in media_dir/EXP.json manifests in place (all, or just exps).
    Only those fields change; every other byte of meaning stays. Returns {exp: n_added}. When stats is given it
    gets "pending" (strings that needed a translation) and "untranslated" (of those, how many got none)."""
    media_dir = Path(media_dir)
    names = sorted(p for p in media_dir.glob("*.json") if p.name != "index.json")
    if exps:
        if missing := sorted(set(exps) - {p.stem for p in names}):
            log(f"[pwa] translate-media: no manifest for {' '.join(missing)}")
        names = [p for p in names if p.stem in set(exps)]
    mans = {}
    for p in names:
        try:
            man = json.loads(p.read_text())
        except (OSError, ValueError) as e:
            log(f"[pwa] translate-media: {p.name} skipped ({type(e).__name__})")
            continue
        tasks = man.get("tasks") if isinstance(man, dict) else None
        if isinstance(tasks, list):
            mans[p] = (man, [t for t in tasks if isinstance(t, dict)])
    pending = list(dict.fromkeys(t[f] for _, rows in mans.values() for t in rows for f in FIELDS
                                 if needs_translation(t.get(f) or "") and not t.get(f + "_en")))
    tr = translate(pending, cache_path, client) if pending else {}  # batched calls across every manifest
    if stats is not None:
        stats.update(pending=len(pending), untranslated=sum(1 for x in pending if x not in tr))
    done = {}
    for p, (man, rows) in mans.items():
        n = 0
        for t in rows:
            for f in FIELDS:
                if not t.get(f + "_en") and tr.get(t.get(f) or ""):
                    t[f + "_en"] = tr[t[f]]
                    n += 1
        if n:
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n")
            tmp.replace(p)
        done[p.stem] = n
    return done
