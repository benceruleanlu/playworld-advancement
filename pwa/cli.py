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
screening judge (dev loops only; never the csv, never a reported number):
  pwa score anchor-v1-dev --judge-model gemini-4-hydrogen [--judge-thinking low]
  pwa cells base-sana-dev anchor-v1-dev --judge-model gemini-4-hydrogen
  pwa score anchor-v1-dev --judge-model openai:gpt-6-luna          # OpenAI-compatible API, JUDGE_API_KEY
  pwa cells base-sana-dev anchor-v1-dev --judge-model gemini-4-hydrogen:low --judge-model openai:gpt-6-luna
  pwa judges base-sana-dev --judge-model gemini-4-hydrogen:low --judge-model openai:gpt-6-luna   # calibration
proxy judge while Gemini credits are out (A/B only; results/proxy_experiments.csv, never a final number):
  pwa score anchor-v1-dev --judge openai [--judge-model gpt-4.1]   # OpenAI key: JUDGE_API_KEY else PLAYER_API_KEY
  pwa compare base-sana-dev anchor-v1-dev --judge openai
extra runner args go after `--`, e.g.  pwa gen X --runner sana -- --num-chunks 20 --seed 1
exit codes: 0 ok, 1 failure (some task failed / check failed), 2 usage error.
config/env.sh is sourced automatically (existing env vars win).
env overrides: PWA_ROOT (repo), PWA_RUNS (runs dir), PWA_RESULTS_CSV (experiment log)."""


def _sel_args(p, default_split=None):
    p.add_argument("--split", default=None, help="dev | dev2 | dev48 | heldout | all | path to TSV (default: "
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
    p.add_argument("--max-chunks", type=int, default=None, metavar="N",
                   help="smoke tier: cap each closed-loop rollout at N agent chunks (passed to the runner as upstream "
                        "--num-chunks, default 30). Labelled a capped smoke run everywhere; never an official score")


def _warn_caps(exp_a: str, exp_b: str) -> list:
    """Chunk caps of A and B; warns when they differ (the delta then mixes the method with the horizon)."""
    from .panel import caps_differ
    caps = [core.chunk_cap(core.read_meta(e)) for e in (exp_a, exp_b)]
    if caps[0] != caps[1]:
        log(f"[pwa] WARNING: {caps_differ(*caps)}")
    return caps


def _judge_args(p, panel: bool = False, required: bool = False):
    more = ("; repeat for a panel of judges" if panel else "")
    p.add_argument("--judge-model", action="append", default=None, required=required, metavar="[openai:]MODEL[:THINKING]",
                   help="screening judge: same verifier with another model, results in runs/EXP/eval-<slug>/; never "
                        "written to results/experiments.csv. No prefix = Gemini; openai: = OpenAI-compatible chat API "
                        "(JUDGE_API_URL/JUDGE_API_KEY, else PLAYER_API_*); :THINKING = minimal|low|medium|high"
                        + more + " (default: official judge, $GEMINI_MODEL, eval/)")
    p.add_argument("--judge", default=None, choices=["gemini", "openai"],
                   help="openai = PROXY judge for A/B while Gemini cannot be called: --judge-model openai:MODEL, "
                        "MODEL from --judge-model (prefix optional) else $PWA_PROXY_JUDGE_MODEL else gpt-4.1; "
                        "runs/EXP/eval-openai-MODEL/, rows in results/proxy_experiments.csv. Uncalibrated against "
                        "Gemini: same-run control vs treatment only. gemini (default) = unchanged")
    p.add_argument("--judge-thinking", default=None, choices=["minimal", "low", "medium", "high"],
                   help="one screening judge only: thinking level (Gemini thinking_level, OpenAI reasoning_effort; "
                        "upstream sets none); part of the dir slug")


def _score_args(p):
    p.add_argument("--passes", type=int, default=2, help="verifier passes (default 2)")
    p.add_argument("--workers", type=int, default=4, help="parallel verifier subprocesses (default 4)")
    p.add_argument("--retries", type=int, default=1, help="retries per failed verifier call (default 1)")
    p.add_argument("--dry-run", action="store_true", help="sampling + prompt only, no Gemini; writes eval_dry/")
    p.add_argument("--force", action="store_true", help="rescore even if result files exist")
    _judge_args(p, panel=True)


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

    p = mk("gen-arms", "generate several arms (runner arg strings) into EXP-a1, EXP-a2, ... in one process, "
                       "so an in-process runner loads its model once")
    p.add_argument("exp", help="arm group name; arm i writes runs/EXP-a<i>/")
    p.add_argument("--arms", required=True,
                   help="'|'-separated runner arg strings; an empty one is a baseline arm, e.g. ' | --lingbot-turn-cal'. "
                        "Args after `--` go to every arm, before the arm's own")
    _sel_args(p, "dev")
    _gen_args(p)
    p.add_argument("--json", action="store_true", help="print per-arm summary JSON on stdout")

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
    _judge_args(p, panel=True)

    p = mk("compare", "per-family and per-task deltas B - A, with noise flags")
    p.add_argument("exp_a")
    p.add_argument("exp_b")
    _sel_args(p)
    p.add_argument("--json", action="store_true")
    _judge_args(p)

    p = mk("cells", "per-task pass-means of A and B on their common tasks, delta, and tasks moved >= 1.0 up/down")
    p.add_argument("exp_a")
    p.add_argument("exp_b")
    _sel_args(p)
    p.add_argument("--json", action="store_true")
    _judge_args(p, panel=True)

    p = mk("judges", "calibrate screening judges against the official judge on one experiment (screening only; writes nothing)")
    p.add_argument("exp")
    _sel_args(p)
    p.add_argument("--json", action="store_true")
    p.add_argument("--md", action="store_true", help="GitHub markdown table")
    _judge_args(p, panel=True, required=True)

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
    p.add_argument("--proxy", action="store_true",
                   help="copy EXP's proxy-judge rows from results/proxy_experiments.csv instead (keyed by exp, split, judge)")

    p = mk("mark", "record a run's live status (running|generated|failed|cancelled) in a results csv (used by the workflow)")
    p.add_argument("exp")
    p.add_argument("--into", required=True, help="destination experiments.csv (e.g. a checkout of main)")
    p.add_argument("--status", required=True, choices=["running", "generated", "failed", "cancelled"])
    p.add_argument("--split", default="")
    p.add_argument("--runner", default="")
    p.add_argument("--action-source", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--max-chunks", type=int, default=None, help="agent-chunk cap of a capped smoke run (labels the row)")

    p = mk("media", "small web copies of a run's rollouts, a manifest for the results site and SCENES.md play links "
                    "(any run with videos, scored or not; used by the workflow)")
    p.add_argument("exp")
    _sel_args(p)
    p.add_argument("--out", required=True, help="directory for the clips, posters and EXP.json")
    p.add_argument("--base-url", default="", help="URL prefix the assets will be served from (the run's release download URL)")
    p.add_argument("--release-url", default="", help="page that lists all of the run's files")
    p.add_argument("--index", default="", help="index.json to add this run to (e.g. results/media/index.json in a checkout of main)")
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--screening", default="", metavar="JUDGE",
                   help="screening run: name of its screening judge, shown as a label (its scores are never published)")
    p.add_argument("--report-name", default="", help="file under results/reports/ the release notes link to (default EXP.md)")
    p.add_argument("--site-url", default="", help="results site for the play links in SCENES.md (default: the public site)")
    p.add_argument("--label", action="append", default=[], help="extra manifest label (repeatable; the arms workflow adds the arm's args)")

    p = mk("translate-media", "fill missing English reason_en fields in scenes manifests in place (display only; "
                              "one batched Gemini call, GEMINI_API_KEY; the original reason stays authoritative)")
    p.add_argument("--dir", required=True, help="directory of EXP.json manifests, e.g. results/media")
    p.add_argument("--exps", default="", help="comma-separated experiment names, or all (default: every manifest)")
    p.add_argument("--cache", default="", help="translation cache JSON (sha256 of the source text -> English), "
                                               "so a retry calls the API only for strings not yet translated")
    p.add_argument("--json", action="store_true")

    p = mk("failures", "tasks that are missing, gate-failed, or scored 1.0, with the verifier's reason "
                       "(pass closest to the task's mean; English copy when translated)")
    p.add_argument("exp")
    _sel_args(p)
    p.add_argument("--all", action="store_true", help="every task, not only failures")
    p.add_argument("--json", action="store_true")
    p.add_argument("--md", action="store_true", help="GitHub markdown table")
    _judge_args(p)
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


def _join_arms(argv: list[str]) -> list[str]:
    """`--arms VALUE` -> `--arms=VALUE` (before any `--`). argparse rejects a separate value that starts with a
    dash and has no space, e.g. `--arms '--lingbot-turn-cal|--lingbot-stateless'`."""
    out, i = [], 0
    while i < len(argv):
        if argv[i] == "--":
            return out + argv[i:]
        if argv[i] == "--arms" and i + 1 < len(argv) and argv[i + 1] != "--":
            out.append(f"--arms={argv[i + 1]}")
            i += 2
            continue
        out.append(argv[i])
        i += 1
    return out


def main(argv: list[str] | None = None) -> int:
    argv = _join_arms(list(sys.argv[1:] if argv is None else argv))
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    a = parser().parse_args(argv)
    a.extra = extra
    if extra and a.cmd not in ("gen", "gen-arms", "run"):
        log("pwa: extra args after `--` are only for gen/gen-arms/run")
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
    from . import doctor, gen, panel, report, score

    judges = score.judges_of(a)  # validates the judge flags before any work
    if len(judges) > 1 and a.cmd in ("run", "compare", "failures"):
        raise PwaError(f"`pwa {a.cmd}` takes one --judge-model; panels: score, report, cells, judges")

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

    if a.cmd == "gen-arms":
        from . import arms
        s = arms.gen_arms(a, core.select(a.split, a.family, a.tasks))
        if a.json:
            emit(s, True)
        return 1 if s["failed"] else 0

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

    judge = judges[0] if len(judges) == 1 else None

    if a.cmd == "report" and len(judges) > 1:
        sel = core.select_for_exp(a.exp, a.split, a.family, a.tasks)
        reps = [report.report(a.exp, sel, _split_label(a, a.exp), a.strict, judge=j) for j in judges]
        pn = panel.panel(reps)
        emit(pn, a.json, panel.render_panel(pn, a.md))
        return 0 if all(r["passes"] for r in reps) else 1

    if a.cmd == "judges":
        sel = core.select_for_exp(a.exp, a.split, a.family, a.tasks)
        off = report.build(a.exp, sel)
        if not off["passes"]:
            raise PwaError(f"{a.exp} has no official passes in eval/; calibration needs official scores on the same videos")
        reps = [report.build(a.exp, sel, judge=j) for j in judges]
        if missing := [j.spec for j, r in zip(judges, reps) if not r["passes"]]:
            raise PwaError(f"no scored passes for {' '.join(missing)} (run `pwa score {a.exp} --judge-model ...`)")
        c = panel.calibrate(off, reps)
        emit(c, a.json, panel.render_calibration(c, a.md))
        return 0

    if a.cmd == "cells" and len(judges) > 1:
        sa = core.select_for_exp(a.exp_a, a.split, a.family, a.tasks)
        sb = core.select_for_exp(a.exp_b, a.split, a.family, a.tasks)
        common = {t["task_id"] for t in sa} & {t["task_id"] for t in sb}
        if len(common) < max(len(sa), len(sb)):
            log(f"[pwa] task lists differ; comparing on the {len(common)} common tasks")
        caps = _warn_caps(a.exp_a, a.exp_b)
        pairs = [(report.build(a.exp_a, [t for t in sa if t["task_id"] in common], judge=j),
                  report.build(a.exp_b, [t for t in sb if t["task_id"] in common], judge=j)) for j in judges]
        if missing := [j.spec for j, (ra, rb) in zip(judges, pairs) if not ra["passes"] or not rb["passes"]]:
            raise PwaError(f"both experiments need at least one scored pass under every judge; missing: {' '.join(missing)}")
        c = panel.panel_cells(pairs)
        c["max_chunks"] = {"a": caps[0], "b": caps[1]}
        emit(c, a.json, panel.render_panel_cells(c))
        return 0

    if a.cmd in ("report", "run"):
        sel = core.select_for_exp(a.exp, a.split, a.family, a.tasks)
        rep = report.report(a.exp, sel, _split_label(a, a.exp), getattr(a, "strict", False), judge=judge)
        if a.cmd == "report" and a.md and not a.json:
            text = report.render_md(rep, core.read_meta(a.exp), a.site_url)
        else:
            text = report.render(rep, core.read_meta(a.exp))
        emit(rep, a.json, text)
        if a.cmd == "run":
            return 1 if gen_failed or score_failed else 0
        return 0 if rep["passes"] else 1

    if a.cmd in ("compare", "cells"):
        sa = core.select_for_exp(a.exp_a, a.split, a.family, a.tasks)
        sb = core.select_for_exp(a.exp_b, a.split, a.family, a.tasks)
        common = {t["task_id"] for t in sa} & {t["task_id"] for t in sb}
        if len(common) < max(len(sa), len(sb)):
            log(f"[pwa] task lists differ; comparing on the {len(common)} common tasks")
        _warn_caps(a.exp_a, a.exp_b)
        ra = report.build(a.exp_a, [t for t in sa if t["task_id"] in common], judge=judge)
        rb = report.build(a.exp_b, [t for t in sb if t["task_id"] in common], judge=judge)
        if not ra["passes"] or not rb["passes"]:
            where = f"eval-{judge.slug}/" if judge else "eval/"
            raise PwaError(f"both experiments need at least one scored pass in {where}")
        if a.cmd == "cells":
            c = report.cells(ra, rb)
            emit(c, a.json, report.render_cells(c))
            return 0
        c = report.compare(ra, rb)
        emit(c, a.json, report.render_compare(c))
        return 0

    if a.cmd == "upsert-row":
        try:
            n = (report.upsert_row_into(a.exp, report.proxy_csv(), a.into, keys=report.PROXY_KEYS) if a.proxy
                 else report.upsert_row_into(a.exp, core.RESULTS_CSV, a.into))
        except (ValueError, OSError) as e:
            raise PwaError(str(e)) from e
        log(f"[pwa] upserted {n} row(s) for {a.exp} into {a.into}")
        return 0

    if a.cmd == "mark":
        try:
            n = report.mark_row(a.exp, a.into, a.status, a.split, a.runner, a.action_source, a.notes,
                                core.provenance().get("git_sha") or "", a.max_chunks)
        except (ValueError, OSError) as e:
            raise PwaError(str(e)) from e
        log(f"[pwa] marked {a.exp} {a.status} in {a.into} ({n} row(s))")
        return 0

    if a.cmd == "media":
        from . import media
        man = media.build(a.exp, core.select_for_exp(a.exp, a.split, a.family, a.tasks), Path(a.out), a.base_url,
                          a.release_url, a.height, screening=a.screening, report_name=a.report_name,
                          site_url=a.site_url or media.SITE_URL, extra_labels=a.label)
        if man is None:
            emit({"exp": a.exp, "skipped": "pipeline test"}, True)
            return 0
        if a.index:
            media.update_index(Path(a.index), man)
        emit({k: v for k, v in man.items() if k != "tasks"} | {"n_tasks": len(man["tasks"]),
              "n_videos": sum(1 for t in man["tasks"] if t["video"])}, True)
        return 0

    if a.cmd == "translate-media":
        from . import translate
        d = Path(a.dir)
        if not d.is_dir():
            raise PwaError(f"{d} is not a directory")
        exps = [x.strip() for x in a.exps.split(",") if x.strip() and x.strip() != "all"]
        stats: dict = {}
        done = translate.translate_media(d, exps or None, cache_path=Path(a.cache) if a.cache else None, stats=stats)
        emit(done, a.json, "\n".join(f"{k}\t{v} reason(s) translated" for k, v in done.items()) or "(no manifests)")
        if stats.get("untranslated"):
            log(f"[pwa] translate-media: {stats['untranslated']} of {stats['pending']} reason(s) left untranslated")
        # a backfill that translated nothing it was asked to is a failure (report and media never fail on this)
        if stats.get("pending") and stats.get("untranslated") == stats["pending"]:
            return 1
        return 0

    if a.cmd == "failures":
        rows = report.failures(a.exp, core.select_for_exp(a.exp, a.split, a.family, a.tasks), a.all, judge)
        # English display copy first when there is one, then the judge's original (authoritative)
        text = "\n".join(f"{r['task_id']}\t{r['family']}\t{report.f2(r['mean']).strip()}\t"
                         f"{report.passes_cell(r.get('pass_scores'))}\t{','.join(r['status'])}\t"
                         + (f"{r['reason_en']}\toriginal: {r['reason']}" if r.get("reason_en") else r["reason"])
                         for r in rows)
        if a.md:
            text = report.render_failures_md(rows)
        if judge:
            label = f"> **{judge.label}.**\n\n" if a.md else f"*** {judge.label} ***\n"
            text = label + (text or "(no failures)")
        # screening JSON is wrapped so the judge travels with the rows; official output keeps its list shape
        emit({"judge": report.judge_json(judge), "tasks": rows} if judge else rows, a.json, text or "(no failures)")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
