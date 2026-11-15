// Self-check for runinfo.js against the committed results: node src/scripts/runinfo.check.mjs [--print]
// Run from site/. Fails on a broken expectation; --print lists every generated label.
import { readFileSync, readdirSync, existsSync } from "node:fs";
import assert from "node:assert/strict";
import { build, parseArgs, words, difference } from "./runinfo.js";

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
    const t = Date.parse(o.timestamp);
    return { exp: o.exp, runner: o.runner, action_source: o.action_source, notes: o.notes, status: (o.status || "").toLowerCase(),
      overall: num(o.overall), passes: num(o.passes), n_tasks: num(o.n_tasks), max_chunks: num(o.max_chunks), t: isFinite(t) ? t : null };
  });
}
const rows = csv(readFileSync(new URL("experiments.csv", root), "utf8"));
const mdir = new URL("media/", root);
const index = existsSync(mdir) ? JSON.parse(readFileSync(new URL("index.json", mdir), "utf8")) : { runs: [] };
const mans = {};
if (existsSync(mdir)) for (const f of readdirSync(mdir)) if (f !== "index.json" && f.endsWith(".json")) { const m = JSON.parse(readFileSync(new URL(f, mdir), "utf8")); mans[m.exp] = m; }
// fixed clock so a stale "running" row reads the same in CI as when the expectations were written
const RI = build(rows, index.runs, mans, Date.parse("2026-11-15T06:00:00Z"));

// pure parts
assert.deepEqual(parseArgs(["--lingbot-stall-abort", "900", "--lingbot-cond-text=1.0", "--lingbot-fast"]),
  [{ flag: "--lingbot-stall-abort", value: "900" }, { flag: "--lingbot-cond-text", value: "1.0" }, { flag: "--lingbot-fast", value: null }]);
assert.deepEqual(words(["--lingbot-cond-schedule", "--lingbot-cond-text=1.0"]), ["conditioning schedule (text boost off)"]);
assert.deepEqual(words(["--lingbot-new-thing=3"]), ["--lingbot-new-thing 3"], "unknown flags show verbatim");
assert.deepEqual(words(["--lingbot-turn-cal", "--lingbot-yaw-servo", "--lingbot-yaw-servo-k=0.5"]),
  ["turn calibration", "yaw servo (error share 0.5)"]);
assert.deepEqual(words(["--lingbot-turn-cal", "--lingbot-yaw-servo", "--lingbot-yaw-servo-tasks=^[GO][CE]\\d"]),
  ["turn calibration", "yaw servo (yaw servo tasks ^[GO][CE]\\d)"]);
assert.deepEqual(words(["--lingbot-split-sink", "--lingbot-split-sink-fg-scale=0.15", "--lingbot-split-sink-fg-frac=0.3"]),
  ["split sink scaling (fg scale 0.15, fg fraction 0.3)"]);

const lab = (e) => RI.get(e) && RI.get(e).armLabel;
const expect = {
  "rs13-arms-v1-a1": "Control", "rs13-arms-v1-a2": "+ return stop",
  "gch13-arms-v1-a1": "Control", "gch13-arms-v1-a2": "+ GC completion hint",
  "orc14-gc-v1-a1": "Control", "orc14-gc-v1-a2": "+ turn calibration",
  "cs14-fx-v1-a1": "Control", "cs14-fx-v1-a2": "+ conditioning schedule",
  "cs14-fx-v1-a3": "+ conditioning schedule (text boost off)", "cs14-fx-v1-a4": "+ conditioning schedule (all 4 steps)",
  "mem14-fx-v1-a1": "Control", "mem14-fx-v1-a2": "+ keep first 12 latents", "mem14-fx-v1-a3": "+ attend to last 36 latents",
  "mem14-fx-v1-a4": "+ keep first 12 latents, attend to last 36 latents",
  "fx14-model-dev-v2-a1": "Control", "fx14-model-dev-v2-a2": "+ turn calibration",
  "sp14-gc-v1-a1": "Control", "sp14-gc-v1-a2": "+ GC chunk director", "sp14-gc-v1-a3": "+ GC ease turns", "sp14-gc-v1-a4": "+ re-anchor"
};
for (const [e, want] of Object.entries(expect)) assert.equal(lab(e), want, e);
assert.equal(RI.get("sp14-gc-v1-a1").driver, "scripted moves");
assert.equal(RI.get("rs13-arms-v1-a1").size, "1.3B model");
assert.match(RI.group("cs14-fx-v1-a1").label, /^Conditioning schedule test · 14B model · fixed actions · 7 tasks: GC, IF, insight · .* · on top of: caption prompt, turn calibration$/);
assert.match(RI.get("lb14-session-agent-dev-v1").label, /^no flags · 14B model · AI player · 24 tasks, all families · scored, 2 passes$/);
assert.match(RI.get("smk14-gc-fastdit-ctl-c10-v1").label, /^turn calibration, player hint · 14B model · AI player · 1 GC task · capped 10 chunks, not scored$/);
assert.equal(difference(RI.get("rs13-arms-v1-a1"), RI.get("rs13-arms-v1-a2")), "Only difference: return stop.");

if (process.argv.includes("--print")) {
  for (const s of RI.sections(index.runs.map((r) => r.exp).concat(rows.map((r) => r.exp)).filter((e, i, a) => a.indexOf(e) === i))) {
    console.log("## " + s.title);
    for (const b of s.blocks) {
      if (b.group) { console.log("  [" + b.label + "]"); b.items.forEach((i) => console.log("    " + i.armLabel + "  (" + i.exp + ")")); }
      else console.log("  " + b.items[0].label + "  (" + b.items[0].exp + ")");
    }
  }
}
console.log("runinfo check ok");
