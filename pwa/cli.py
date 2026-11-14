"""pwa: PlayWorld iteration CLI. Data on stdout, logs on stderr, --json on read commands."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import core
from .core import FAMILIES, PwaError, log

EPILOG = """\
typical loop:
  pwa doctor
  pwa run base-sana-dev --split dev --runner sana --action-source dataset --passes 2
  pwa run anchor-v1-dev --split dev --runner anchor --action-source dataset --passes 2
  pwa compare base-sana-dev anchor-v1-dev
  pwa failures anchor-v1-dev
extra runner args go after `--`, e.g.  pwa gen X --runner sana -- --num-chunks 20 --seed 1
exit codes: 0 ok, 1 failure (some task failed / check failed), 2 usage error.
config/env.sh is sourced automatically (existing env vars win).
env overrides: PWA_ROOT (repo), PWA_RUNS (runs dir), PWA_RESULTS_CSV (experiment log)."""


def _sel_args(p, default_split=None):
    p.add_argument("--split", default=None, help="dev | heldout | all | path to TSV (default: "
                   + (default_split or "the task list recorded by `pwa gen`") + "; --tasks alone may name any task)")
    p.add_argument("--family", nargs="+", choices=FAMILIES, help="restrict to families")
    p.add_argument("--tasks", nargs="+", metavar="ID", help="restrict to task ids")


def _gen_args(p):
    p.add_argument("--runner", default="sana", help="sana | adapters/<NAME>/run.py name | path to a run_agent.py-compatible script")
    p.add_argument("--action-source", default="dataset", choices=["dataset", "agent", "dataset_then_agent", "refined"],
                   help="dataset = open-loop replay (fast A/B); agent/refined = closed loop (final numbers)")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--num-shards", type=int, default=1)
    p.add_argument("--resume", action="store_true", help="reuse an existing runs/EXP (upstream skips tasks whose mp4 exists)")
    p.add_argument("--notes", default="", help="free text stored in meta.json and results/experiments.csv")


def _score_args(p):
    p.add_argument("--passes", type=int, default=2, help="verifier passes (default 2)")
    p.add_argument("--workers", type=int, default=4, help="parallel verifier subprocesses (default 4)")
    p.add_argument("--retries", type=int, default=1, help="retries per failed verifier call (default 1)")
    p.add_argument("--dry-run", action="store_true", help="sampling + prompt only, no Gemini; writes eval_dry/")
    p.add_argument("--force", action="store_true", help="rescore even if result files exist")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pwa", description=__doc__, epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")
    mk = lambda name, help_: sub.add_parser(name, help=help_, description=help_)  # noqa: E731

    p = mk("doctor", "check environment, data, keys (values never printed)")
    p.add_argument("--for", dest="action", default="all", choices=["all", "gen", "score"],
                   help="exit 1 only if something needed for this action is missing")
    p.add_argument("--runner", default="sana")
    p.add_argument("--json", action="store_true")

    p = mk("tasks", "list tasks in a split")
    _sel_args(p, "dev")
    p.add_argument("--json", action="store_true")

    p = mk("gen", "generate rollouts into runs/EXP/videos via a runner")
    p.add_argument("exp")
    _sel_args(p, "dev")
    _gen_args(p)
    p.add_argument("--json", action="store_true", help="print summary JSON on stdout")

    p = mk("score", "run the Rubric Verifier (score + gate) on runs/EXP videos")
    p.add_argument("exp")
    _sel_args(p)
    _score_args(p)
    p.add_argument("--json", action="store_true", help="print summary JSON on stdout")

    p = mk("report", "per-family means, std across passes; updates results/experiments.csv")
    p.add_argument("exp")
    _sel_args(p)
    p.add_argument("--strict", action="store_true", help="count unscored/no-review rollouts as 1.0 (not written to csv)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--md", action="store_true", help="GitHub markdown output (for $GITHUB_STEP_SUMMARY)")
    p.add_argument("--site-url", default=None, help="link to append in --md output")

    p = mk("compare", "per-family and per-task deltas B - A, with noise flags")
    p.add_argument("exp_a")
    p.add_argument("exp_b")
    _sel_args(p)
    p.add_argument("--json", action="store_true")

    p = mk("ls", "list experiments and their status")
    p.add_argument("--json", action="store_true")

    p = mk("preview", "export the contact sheets the judge sees (verifier dry run)")
    p.add_argument("exp")
    p.add_argument("task")
    p.add_argument("--json", action="store_true")

    p = mk("run", "gen + score + report")
    p.add_argument("exp")
    _sel_args(p, "dev")
    _gen_args(p)
    _score_args(p)
    p.add_argument("--json", action="store_true", help="print report JSON on stdout")

    p = mk("upsert-row", "copy EXP's row from this checkout's results csv into another csv (used by the workflow)")
    p.add_argument("exp")
    p.add_argument("--into", required=True, help="destination experiments.csv (e.g. a checkout of main)")

    p = mk("mark", "record a run's live status (running|generated|failed|cancelled) in a results csv (used by the workflow)")
    p.add_argument("exp")
    p.add_argument("--into", required=True, help="destination experiments.csv (e.g. a checkout of main)")
    p.add_argument("--status", required=True, choices=["running", "generated", "failed", "cancelled"])
    p.add_argument("--split", default="")
    p.add_argument("--runner", default="")
    p.add_argument("--action-source", default="")
    p.add_argument("--notes", default="")

    p = mk("media", "small web copies of a run's rollouts plus a manifest for the results site (used by the workflow)")
    p.add_argument("exp")
    _sel_args(p)
    p.add_argument("--out", required=True, help="directory for the clips, posters and EXP.json")
    p.add_argument("--base-url", default="", help="URL prefix the assets will be served from (the run's release download URL)")
    p.add_argument("--release-url", default="", help="page that lists all of the run's files")
    p.add_argument("--index", default="", help="index.json to add this run to (e.g. results/media/index.json in a checkout of main)")
    p.add_argument("--height", type=int, default=480)

    p = mk("failures", "tasks that are missing, gate-failed, or scored 1.0, with the verifier's reason")
    p.add_argument("exp")
    _sel_args(p)
    p.add_argument("--all", action="store_true", help="every task, not only failures")
    p.add_argument("--json", action="store_true")
    p.add_argument("--md", action="store_true", help="GitHub markdown table")
    return ap


def emit(obj, as_json: bool, text: str | None = None) -> None:
    if as_json or text is None:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _split_label(a, exp: str) -> str:
    if a.cmd == "run" or a.split or a.family or a.tasks:
        return core.split_label(a.split, a.family, a.tasks)
    meta = core.read_meta(exp)
    return meta.get("split_label") or meta.get("split") or "custom"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    a = parser().parse_args(argv)
    a.extra = extra
    if extra and a.cmd not in ("gen", "run"):
        log("pwa: extra args after `--` are only for gen/run")
        return 2
    core.load_env()
    try:
        return dispatch(a)
    except PwaError as e:
        log(f"pwa: {e}")
        return e.code
    except KeyboardInterrupt:
        return 130


def dispatch(a) -> int:  # noqa: C901
    from . import doctor, gen, report, score

    if a.cmd == "doctor":
        res = doctor.checks(a.runner)
        bad = doctor.failing(res, a.action)
        if a.json:
            emit({"ok": not bad, "checks": res}, True)
        else:
            for r in res:
                need = ",".join(r["needed_for"]) or "optional"
                mark = "ok  " if r["ok"] else ("FAIL" if r in bad else "warn")
                print(f"{mark}  {r['check']:<38} [{need}]" + (f"  -> {r['fix']}" if r["fix"] else ""))
        return 1 if bad else 0

    if a.cmd == "tasks":
        sel = core.select(a.split, a.family, a.tasks)
        emit(sel, a.json, "\n".join(f"{t['family']}\t{t['task_id']}\t{t['view']}" for t in sel))
        return 0

    if a.cmd == "ls":
        rows = report.ls()
        text = "\n".join(f"{r['exp']:<28} gen={r['gen']:<7} videos={r['videos']}/{r['expected']} "
                         f"passes={len(r['passes'])} overall={report.f2(r['overall']).strip()} "
                         f"runner={r['runner']} src={r['action_source']}" for r in rows)
        emit(rows, a.json, text or "(no experiments)")
        return 0

    if a.cmd == "preview":
        info = core.task_info(core.family_of(a.task), a.task)
        d = score.preview(a.exp, info)
        emit({"dir": str(d)}, a.json, str(d))
        return 0

    if a.cmd in ("gen", "run"):
        sel = core.select(a.split, a.family, a.tasks)
        s = gen.gen(a, sel)
        if a.cmd == "gen":
            if a.json:
                emit(s, True)
            return 1 if s["failed"] or s["runner_errors"] else 0
        gen_failed = bool(s["failed"] or s["runner_errors"])
        if s["produced"] == 0:
            raise PwaError("no videos produced; not scoring")

    if a.cmd in ("score", "run"):
        sel = core.select_for_exp(a.exp, a.split, a.family, a.tasks)
        s = score.score(a, sel)
        if a.cmd == "score":
            if a.json:
                emit(s, True)
            return 1 if s["failed"] else 0
        score_failed = bool(s["failed"])
        if a.dry_run:
            log("[pwa] dry run: skipping report")
            return 1 if gen_failed or score_failed else 0

    if a.cmd in ("report", "run"):
        sel = core.select_for_exp(a.exp, a.split, a.family, a.tasks)
        rep = report.report(a.exp, sel, _split_label(a, a.exp), getattr(a, "strict", False))
        if a.cmd == "report" and a.md and not a.json:
            text = report.render_md(rep, core.read_meta(a.exp), a.site_url)
        else:
            text = report.render(rep, core.read_meta(a.exp))
        emit(rep, a.json, text)
        if a.cmd == "run":
            return 1 if gen_failed or score_failed else 0
        return 0 if rep["passes"] else 1

    if a.cmd == "compare":
        sa = core.select_for_exp(a.exp_a, a.split, a.family, a.tasks)
        sb = core.select_for_exp(a.exp_b, a.split, a.family, a.tasks)
        common = {t["task_id"] for t in sa} & {t["task_id"] for t in sb}
        if len(common) < max(len(sa), len(sb)):
            log(f"[pwa] task lists differ; comparing on the {len(common)} common tasks")
        ra = report.build(a.exp_a, [t for t in sa if t["task_id"] in common])
        rb = report.build(a.exp_b, [t for t in sb if t["task_id"] in common])
        if not ra["passes"] or not rb["passes"]:
            raise PwaError("both experiments need at least one scored pass")
        c = report.compare(ra, rb)
        emit(c, a.json, report.render_compare(c))
        return 0

    if a.cmd == "upsert-row":
        try:
            n = report.upsert_row_into(a.exp, core.RESULTS_CSV, a.into)
        except (ValueError, OSError) as e:
            raise PwaError(str(e)) from e
        log(f"[pwa] upserted {n} row(s) for {a.exp} into {a.into}")
        return 0

    if a.cmd == "mark":
        try:
            n = report.mark_row(a.exp, a.into, a.status, a.split, a.runner, a.action_source, a.notes,
                                core.provenance().get("git_sha") or "")
        except (ValueError, OSError) as e:
            raise PwaError(str(e)) from e
        log(f"[pwa] marked {a.exp} {a.status} in {a.into} ({n} row(s))")
        return 0

    if a.cmd == "media":
        from . import media
        man = media.build(a.exp, core.select_for_exp(a.exp, a.split, a.family, a.tasks), Path(a.out), a.base_url,
                          a.release_url, a.height)
        if a.index:
            media.update_index(Path(a.index), man)
        emit({k: v for k, v in man.items() if k != "tasks"} | {"n_tasks": len(man["tasks"]),
              "n_videos": sum(1 for t in man["tasks"] if t["video"])}, True)
        return 0

    if a.cmd == "failures":
        rows = report.failures(a.exp, core.select_for_exp(a.exp, a.split, a.family, a.tasks), a.all)
        text = "\n".join(f"{r['task_id']}\t{r['family']}\t{report.f2(r['mean']).strip()}\t"
                         f"{','.join(r['status'])}\t{r['reason']}" for r in rows)
        if a.md:
            text = report.render_failures_md(rows)
        emit(rows, a.json, text or "(no failures)")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
