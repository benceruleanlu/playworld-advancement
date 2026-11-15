// Self-check for pairs.js: node src/scripts/pairs.check.mjs [--print]
// Run from site/. Part 1 derives pairs from the committed results (experiments.csv, results/media); part 2 from a
// small stubbed CSV and manifests; part 3 round-trips the URL state. --print lists every comparison with its count.
import { readFileSync, readdirSync, existsSync } from "node:fs";
import assert from "node:assert/strict";
import { build } from "./runinfo.js";
import { derivePairs, findComparison, filterPairs, seedsOf, pairId, pairById, readState, writeState, mapLegacy } from "./pairs.js";

const root = new URL("../../../results/", import.meta.url);
function csv(text) {
  const rows = []; let row = [], f = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; continue; }
    if (c === '"') q = true; else if (c === ",") { row.push(f); f = ""; } else if (c === "\n") { row.push(f); rows.push(row); row = []; f = ""; } else if (c !== "\r") f += c;
  }
  if (f || row.length) { row.push(f); rows.push(row); }
  const head = rows[0];
  const num = (s) => (s === undefined || s.trim() === "" || !isFinite(+s) ? null : +s);
  return rows.slice(1).filter((r) => r[0]).map((r) => {
    const o = {}; head.forEach((h, j) => (o[h] = r[j] ?? ""));
    return { exp: o.exp, runner: o.runner, action_source: o.action_source, notes: o.notes, status: (o.status || "").toLowerCase(),
      overall: num(o.overall), passes: num(o.passes), n_tasks: num(o.n_tasks), max_chunks: num(o.max_chunks), t: null };
  });
}
const NOW = Date.parse("2026-11-15T12:00:00Z");
let failed = 0;
function check(name, fn) {
  try { fn(); } catch (e) { failed++; console.error("FAIL " + name + ": " + e.message); }
}

/* ---------- 1. real data ---------- */
const mdir = new URL("media/", root);
if (existsSync(mdir)) {
  const rows = csv(readFileSync(new URL("experiments.csv", root), "utf8"));
  const index = JSON.parse(readFileSync(new URL("index.json", mdir), "utf8"));
  const mans = {};
  for (const f of readdirSync(mdir)) if (f !== "index.json" && f.endsWith(".json")) { const m = JSON.parse(readFileSync(new URL(f, mdir), "utf8")); mans[m.exp] = m; }
  const RI = build(rows, index.runs, mans, NOW);
  const D = derivePairs(index, mans, RI);
  const all = D.comparisons.flatMap((c) => c.pairs);
  const of = (trt) => all.filter((p) => p.trt === trt);
  const ctlOf = (trt) => [...new Set(of(trt).map((p) => p.ctl))];

  check("stack seed 0 pairs a2 with a1", () => assert.deepEqual(ctlOf("stk14-fx-dev-v1-a2"), ["stk14-fx-dev-v1-a1"]));
  check("stack seed 1 pairs a4 with a3", () => assert.deepEqual(ctlOf("stk14-fx-dev-v1-a4"), ["stk14-fx-dev-v1-a3"]));
  check("a3 is never a treatment of a1", () => assert.equal(all.filter((p) => p.ctl === "stk14-fx-dev-v1-a1" && p.trt === "stk14-fx-dev-v1-a3").length, 0));
  check("72 stack pairs in one comparison", () => {
    const c = D.comparisons.find((x) => x.pairs.some((p) => p.trt === "stk14-fx-dev-v1-a2"));
    assert.ok(c); assert.equal(c.pairs.length, 72);
    assert.ok(c.pairs.some((p) => p.trt === "stk14-fx-dev-v1-a4") && c.pairs.some((p) => p.trt === "stk14-fx-dev2-v1-a2"));
    assert.deepEqual(seedsOf(c), ["0", "1"]);
  });
  check("sv14-a2 control is win14-a3, 8 pairs, no GC005", () => {
    assert.deepEqual(ctlOf("sv14-fx-v1-a2"), ["win14-fx-v1-a3"]);
    assert.equal(of("sv14-fx-v1-a2").length, 8);
    assert.ok(!of("sv14-fx-v1-a2").some((p) => p.task === "GC005"));
    assert.ok(of("sv14-fx-v1-a2").every((p) => p.cross && p.shaDiff));
  });
  check("sv14-a1: 8 pairs, mem14-a1 except OE058 from sks14-a1", () => {
    const ps = of("sv14-fx-v1-a1");
    assert.equal(ps.length, 8);
    ps.forEach((p) => assert.equal(p.ctl, p.task === "OE058" ? "sks14-fx-v1-a1" : "mem14-fx-v1-a1", p.task));
    assert.ok(ps.some((p) => p.task === "OE058"));
    assert.ok(!ps.some((p) => p.task === "GC005"));
  });
  check("win14-a2 and pm14-fx-v2-a1 are never a control", () => {
    assert.equal(all.filter((p) => p.ctl === "win14-fx-v1-a2" || p.ctl === "pm14-fx-v2-a1").length, 0);
  });
  check("pm14-fx-v2 arms pair with pm14-fx-v1-a1", () => {
    ["a1", "a2", "a3", "a4"].forEach((a) => assert.deepEqual(ctlOf("pm14-fx-v2-" + a), ["pm14-fx-v1-a1"], a));
  });
  check("pm14-fx-v3 arms pair with their root control a1", () => {
    assert.deepEqual(ctlOf("pm14-fx-v3-a2"), ["pm14-fx-v3-a1"]);
    assert.deepEqual(ctlOf("pm14-fx-v3-a3"), ["pm14-fx-v3-a1"]);
  });
  check("servo on the stack base and on caption+turn-cal are separate comparisons", () => {
    const a = D.byTriple["GC033|svgc14-fx-v1-a1|svgc14-fx-v1-a2"], b = Object.entries(D.byTriple).find(([k]) => k.endsWith("|stksv14-fx-gc-v1-a1|stksv14-fx-gc-v1-a2"));
    assert.ok(a && b && a !== b[1]);
  });
  check("closed-loop comparisons say the actions differ", () => {
    const c = findComparison(D, D.byTriple[Object.keys(D.byTriple).find((k) => k.endsWith("|stksv14-cl-gc-v1-a1|stksv14-cl-gc-v1-a2"))]);
    assert.ok(c && c.section === "agent" && /actions differ/.test(c.label));
  });
  check("no pair has differing seeds or drivers", () => {
    all.forEach((p) => {
      const c = RI.get(p.ctl), t = RI.get(p.trt);
      assert.equal(c.driver, t.driver, p.trt);
      const seed = (e) => ((mans[e].runner_args || []).join(" ").match(/--seed[ =](\d+)/) || [0, "0"])[1];
      assert.equal(seed(p.ctl), seed(p.trt), p.task + " " + p.trt);
    });
  });
  check("every pair has both clips", () => all.forEach((p) => {
    [p.ctl, p.trt].forEach((e) => assert.ok(mans[e].tasks.some((t) => t.task_id === p.task && /^https:/.test(t.video)), e + " " + p.task));
  }));
  check("seed repeats pair same flags across seeds only", () => {
    assert.ok(D.repeats.length > 0);
    D.repeats.forEach((r) => r.pairs.forEach((p) => assert.equal(p.ctl.split("-a")[0], p.trt.split("-a")[0])));
    assert.ok(D.repeats.some((r) => r.runs.includes("stk14-fx-dev-v1-a1") && r.runs.includes("stk14-fx-dev-v1-a3")));
  });
  check("comparison keys are unique", () => {
    const ks = D.comparisons.concat(D.repeats).map((c) => c.key);
    assert.equal(new Set(ks).size, ks.length);
  });
  check("legacy links map", () => {
    assert.ok(mapLegacy(D, "OE039", "stk14-fx-dev-v1-a1", "stk14-fx-dev-v1-a2"));
    assert.ok(mapLegacy(D, "GC033", "svgc14-fx-v1-a1", "svgc14-fx-v1-a2"));
    assert.equal(mapLegacy(D, "OE039", "stk14-fx-dev-v1-a1", "stk14-fx-dev-v1-a4"), null);
  });
  if (process.argv.includes("--print")) {
    D.comparisons.forEach((c) => console.log(String(c.pairs.length).padStart(3), c.section.padEnd(8), c.key, "::", c.label));
    D.repeats.forEach((c) => console.log(String(c.pairs.length).padStart(3), "repeats ", c.key, "::", c.label));
    console.log("total", all.length, "pairs from", new Set(all.flatMap((p) => [p.ctl, p.trt])).size, "runs");
  }
}

/* ---------- 2. stubbed CSV and manifests ---------- */
{
  const clip = (exp, task, fam) => ({ task_id: task, family: fam, mean: null, status: [], video: "https://x/" + exp + "/" + task + ".mp4", poster: "https://x/" + exp + "/" + task + ".jpg" });
  const man = (exp, args, tasks, extra) => Object.assign({ exp, runner: "lingbot_world2", action_source: "dataset", runner_args: args, git_sha: "aaaaaaa", notes: "",
    tasks: tasks.map(([t, f]) => clip(exp, t, f)) }, extra || {});
  const arm = (g, i, n, args) => ({ exp: g + "-a" + i, runner: "lingbot_world2", action_source: "dataset", notes: "[arm " + i + "/" + n + " of " + g + ": " + args + "]", status: "generated", overall: null, passes: null, n_tasks: 2, max_chunks: null, t: null });
  const rows = [
    arm("t1", 1, 4, ""), arm("t1", 2, 4, "--lingbot-yaw-servo"), arm("t1", 3, 4, "--seed 1"), arm("t1", 4, 4, "--seed 1 --lingbot-yaw-servo"),
    arm("t2", 1, 1, "--lingbot-turn-cal --lingbot-yaw-servo"),
    arm("t3", 1, 2, "--agent-model m"), arm("t3", 2, 2, "--agent-model m --lingbot-turn-cal")
  ];
  const mans = {
    "t1-a1": man("t1-a1", [], [["GC1", "gc"], ["OE1", "outsight"]]),
    "t1-a2": man("t1-a2", ["--lingbot-yaw-servo"], [["GC1", "gc"], ["OE1", "outsight"], ["OE2", "outsight"]]),
    "t1-a3": man("t1-a3", ["--seed", "1"], [["GC1", "gc"]]),
    "t1-a4": man("t1-a4", ["--seed", "1", "--lingbot-yaw-servo"], [["GC1", "gc"]], { git_sha: "bbbbbbb" }),
    // named control in notes; t1-a1 has no turn-cal so it is not a subset candidate... it is: {} is a subset of anything
    "t2-a1": man("t2-a1", ["--lingbot-turn-cal", "--lingbot-yaw-servo"], [["GC1", "gc"]], { notes: "servo on turn-cal, control t1-a2", git_sha: "ccccccc" }),
    "t3-a1": man("t3-a1", ["--agent-model", "m"], [["IF1", "if"]], { action_source: "agent", player_model: "m" }),
    "t3-a2": man("t3-a2", ["--agent-model", "m", "--lingbot-turn-cal"], [["IF1", "if"]], { action_source: "agent", player_model: "m" })
  };
  const index = { runs: Object.keys(mans).map((exp) => ({ exp, generated: "2026-11-15T00:00:00Z" })) };
  const RI = build(rows, index.runs, mans, NOW);
  const D = derivePairs(index, mans, RI);
  const all = D.comparisons.flatMap((c) => c.pairs);
  check("stub: seed split", () => {
    assert.deepEqual(all.filter((p) => p.trt === "t1-a2").map((p) => p.ctl + ":" + p.task), ["t1-a1:GC1", "t1-a1:OE1"]);
    assert.deepEqual(all.filter((p) => p.trt === "t1-a4").map((p) => p.ctl), ["t1-a3"]);
    assert.ok(all.find((p) => p.trt === "t1-a4").shaDiff === true);
  });
  check("stub: missing control clip means no pair", () => assert.ok(!all.some((p) => p.task === "OE2")));
  check("stub: named control with fewest flags, cross-run", () => {
    const p = all.find((x) => x.trt === "t2-a1");
    assert.equal(p.ctl, "t1-a2"); assert.ok(p.cross && p.shaDiff);
  });
  check("stub: closed loop section and label", () => {
    const c = D.comparisons.find((x) => x.pairs.some((p) => p.trt === "t3-a2"));
    assert.equal(c.section, "agent"); assert.match(c.label, /actions differ/);
  });
  check("stub: servo on two bases is two comparisons", () => {
    const k1 = D.byTriple["GC1|t1-a1|t1-a2"], k2 = D.byTriple["GC1|t1-a2|t2-a1"];
    assert.ok(k1 && k2 && k1 !== k2);
    assert.equal(D.byTriple["GC1|t1-a3|t1-a4"], k1);
  });
  check("stub: repeats", () => {
    assert.ok(D.repeats.some((r) => r.runs.join() === "t1-a1,t1-a3"));
    assert.ok(D.repeats.some((r) => r.runs.join() === "t1-a2,t1-a4"));
  });
  check("stub: filters and ids", () => {
    const c = findComparison(D, D.byTriple["GC1|t1-a1|t1-a2"]);
    assert.equal(filterPairs(c, "gc", "").length, 2);
    assert.equal(filterPairs(c, "", "1").length, 1);
    const list = filterPairs(c, "", "");
    const id = pairId(list, list[0]);
    assert.equal(id, "GC1~t1-a1");
    assert.equal(pairById(list, id), 0);
    assert.equal(pairById(list, "OE1"), list.findIndex((p) => p.task === "OE1"));
  });
}

/* ---------- 3. URL state round trip ---------- */
check("url round trip", () => {
  const st = { cmp: "yaw-servo-on-caption", fam: "gc", seed: "1", pair: "GC033~sv-a1" };
  const qs = writeState("?compare=GC033&b=x&c=y&tour=2&csv=experiments.csv", st);
  const q = new URLSearchParams(qs);
  assert.equal(q.get("compare"), null); assert.equal(q.get("b"), null);
  assert.equal(q.get("tour"), "2"); assert.equal(q.get("csv"), "experiments.csv");
  assert.deepEqual(readState("?" + qs), st);
  assert.deepEqual(readState("?" + writeState("?cmp=a&fam=gc", { cmp: "a", fam: "", seed: "", pair: "" })), { cmp: "a", fam: "", seed: "", pair: "" });
});

if (failed) { console.error(failed + " pairs check(s) failed"); process.exit(1); }
console.log("pairs.check: ok");
