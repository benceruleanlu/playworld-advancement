// Plain-language run descriptions, derived from data: results/experiments.csv rows, the Scenes index
// (results/media/index.json) and per-run manifests. Pure functions, no DOM; used by app.js and compare.js,
// checked by runinfo.check.mjs. A new runner flag needs a FLAG_NAMES entry; unknown flags show verbatim.

// runner arg -> plain words. A function gets the flag's value. Knob flags name their parent flag and render
// inside it, e.g. "conditioning schedule (text boost off)".
export const FLAG_NAMES = {
  "--lingbot-stateless": "no session memory",
  "--lingbot-turn-cal": "turn calibration",
  "--lingbot-caption-prompt": "caption prompt",
  "--lingbot-reanchor": "re-anchor",
  "--lingbot-player-hint": "player hint",
  "--lingbot-return-stop": "return stop",
  "--lingbot-gc-completion-hint": "GC completion hint",
  "--lingbot-if-horizon": "IF horizon",
  "--lingbot-if-camera-hint": "IF camera hint",
  "--lingbot-player-history-endpoints": "player history endpoints",
  "--lingbot-insight-director": "insight director",
  "--lingbot-if-repeat-check": "IF repeat check",
  "--lingbot-if-slow-translation": "IF slow translation",
  "--lingbot-gc-chunk-director": "GC chunk director",
  "--lingbot-gc-ease-turns": "GC ease turns",
  "--lingbot-if-subject-director": "IF subject director",
  "--lingbot-weight-mod": "weight modulation",
  "--lingbot-if-identity-cue": "IF identity cue",
  "--lingbot-measured-turn": "measured turn",
  "--lingbot-noise-mean-coupling": "noise mean coupling",
  "--lingbot-cond-schedule": "conditioning schedule",
  "--lingbot-cond-early": function (v) { return +v === 4 ? "all 4 steps" : "first " + v + " steps"; },
  "--lingbot-cond-text": function (v) { return +v === 1 ? "text boost off" : "text boost x" + v; },
  "--lingbot-cond-cam": function (v) { return "still-camera weight " + v; },
  "--lingbot-cond-3p": function (v) { return "third-person camera weight " + v; },
  "--lingbot-sink-size": function (v) { return "keep first " + v + " latents"; },
  "--lingbot-local-attn": function (v) { return +v === -1 ? "full attention" : "attend to last " + v + " latents"; },
  "--lingbot-sink-key-scale": function (v) { return "sink key scale " + v; },
  "--lingbot-sink-scale-after": function (v) { return "from chunk " + v; },
  "--lingbot-sink-scale-tasks": function (v) { return "tasks " + v; },
  "--lingbot-split-sink": "split sink scaling",
  "--lingbot-split-sink-fg-scale": function (v) { return "fg scale " + v; },
  "--lingbot-split-sink-bg-scale": function (v) { return "bg scale " + v; },
  "--lingbot-split-sink-fg-frac": function (v) { return "fg fraction " + v; },
  "--lingbot-split-sink-after": function (v) { return "from chunk " + v; },
  "--lingbot-split-sink-tasks": function (v) { return "tasks " + v; },
  "--lingbot-pose-memory": "pose memory",
  "--lingbot-pose-mem-deg": function (v) { return "match within " + v + " degrees"; },
  "--lingbot-pose-mem-trans": function (v) { return "match within " + v + " units"; },
  "--lingbot-pose-mem-leave-deg": function (v) { return "left after " + v + " degrees"; },
  "--lingbot-pose-mem-leave-trans": function (v) { return "left after " + v + " units"; },
  "--lingbot-pose-mem-latents": function (v) { return v + " recalled latents"; },
  "--lingbot-pose-mem-anchor": function (v) { return "keep " + v + " first latents"; },
  "--lingbot-pose-mem-time": function (v) { return "recall time " + v; },
  "--lingbot-pose-mem-fallback": function (v) { return "no match: " + v; },
  "--lingbot-pose-mem-tasks": function (v) { return "tasks " + v; },
  "--lingbot-pose-mem-max-mb": function (v) { return "bank cap " + v + " MB"; },
  "--lingbot-kv-noise": "noisy memory writes",
  "--lingbot-kv-noise-t": function (v) { return "noise level " + v; },
  "--lingbot-stg": "step-0 self-guidance",
  "--lingbot-stg-steps": function (v) { return v + " guided steps"; },
  "--lingbot-stg-blocks": function (v) { return "blocks " + v; },
  "--lingbot-stg-w": function (v) { return "weight " + v; },
  "--lingbot-turn-step": function (v) { return "turn step " + v + " degrees"; },
  "--lingbot-yaw-gain": function (v) { return "yaw gain " + v; },
  "--lingbot-yaw-gain-left": function (v) { return "yaw gain left " + v; },
  "--lingbot-yaw-gain-right": function (v) { return "yaw gain right " + v; },
  "--player-reasoning-effort": function (v) { return "player effort " + v; },
  "--player-max-completion-tokens": function (v) { return "player max tokens " + v; },
  "--player-empty-retries": function (v) { return "player retries " + v; }
};
// knob -> the flag it tunes
var KNOB_OF = {
  "--lingbot-cond-early": "--lingbot-cond-schedule", "--lingbot-cond-text": "--lingbot-cond-schedule",
  "--lingbot-cond-cam": "--lingbot-cond-schedule", "--lingbot-cond-3p": "--lingbot-cond-schedule",
  "--lingbot-sink-scale-after": "--lingbot-sink-key-scale", "--lingbot-sink-scale-tasks": "--lingbot-sink-key-scale",
  "--lingbot-split-sink-fg-scale": "--lingbot-split-sink", "--lingbot-split-sink-bg-scale": "--lingbot-split-sink",
  "--lingbot-split-sink-fg-frac": "--lingbot-split-sink", "--lingbot-split-sink-after": "--lingbot-split-sink",
  "--lingbot-split-sink-tasks": "--lingbot-split-sink",
  "--lingbot-kv-noise-t": "--lingbot-kv-noise",
  "--lingbot-yaw-gain-left": "--lingbot-yaw-gain", "--lingbot-yaw-gain-right": "--lingbot-yaw-gain",
  "--lingbot-pose-mem-deg": "--lingbot-pose-memory", "--lingbot-pose-mem-trans": "--lingbot-pose-memory", "--lingbot-pose-mem-leave-deg": "--lingbot-pose-memory",
  "--lingbot-pose-mem-leave-trans": "--lingbot-pose-memory", "--lingbot-pose-mem-latents": "--lingbot-pose-memory",
  "--lingbot-pose-mem-anchor": "--lingbot-pose-memory", "--lingbot-pose-mem-time": "--lingbot-pose-memory", "--lingbot-pose-mem-fallback": "--lingbot-pose-memory",
  "--lingbot-pose-mem-tasks": "--lingbot-pose-memory", "--lingbot-pose-mem-max-mb": "--lingbot-pose-memory",
  "--lingbot-stg-steps": "--lingbot-stg", "--lingbot-stg-blocks": "--lingbot-stg", "--lingbot-stg-w": "--lingbot-stg"
};
// what a value flag tests, for a group title ("Attention window test")
var TOPIC = {
  "--lingbot-sink-size": "attention sink", "--lingbot-local-attn": "attention window",
  "--lingbot-sink-key-scale": "sink key scale", "--lingbot-turn-step": "turn step", "--lingbot-yaw-gain": "yaw gain"
};
// speed, logging and player plumbing: never part of a description. --num-chunks becomes "capped N chunks",
// --agent-model is the player, --lingbot-scripted-player sets the driver.
export const HIDDEN = ["--lingbot-fast", "--lingbot-fast-t5", "--lingbot-fast-load", "--lingbot-fast-y", "--lingbot-t5-gpu",
  "--lingbot-fast-dit", "--lingbot-dit-checksum", "--lingbot-cpu-threads", "--lingbot-stall-abort", "--lingbot-stall-dump",
  "--num-chunks", "--agent-model", "--lingbot-scripted-player"];
// notes of runs that recorded no args: "Luna + turn-cal + player hint"
var NOTE_FLAGS = [
  [/turn[- ]cal/i, "--lingbot-turn-cal"], [/player hint/i, "--lingbot-player-hint"], [/caption prompt/i, "--lingbot-caption-prompt"],
  [/weight[- ]mod/i, "--lingbot-weight-mod"], [/return stop/i, "--lingbot-return-stop"], [/completion hint/i, "--lingbot-gc-completion-hint"],
  [/re-?anchor/i, "--lingbot-reanchor"]
];
var FAM_SHORT = { gc: "GC", if: "IF", insight: "insight", outsight: "out-of-sight" };
var FAM_ORDER = ["gc", "if", "insight", "outsight"];
var STALE_MS = 7 * 3600000;
export const MORE = "__more";
export const SECTIONS = [["scored", "Scored by the official judge"], ["unscored", "Not scored yet"], ["capped", "Capped smoke tests"], ["tests", "Pipeline tests"]];

/* ---------- args ---------- */
// ["--a", "900", "--b=1", "--c"] -> [{flag, value}]; a bare token after a flag is its value
export function parseArgs(a) {
  var out = [];
  if (typeof a === "string") a = a.trim() ? a.trim().split(/\s+/) : [];
  for (var i = 0; i < (a || []).length; i++) {
    var x = a[i];
    if (!/^--/.test(x)) { out.push({ flag: x, value: null }); continue; }
    var eq = x.indexOf("=");
    if (eq > 0) out.push({ flag: x.slice(0, eq), value: x.slice(eq + 1) });
    else if (i + 1 < a.length && !/^--/.test(a[i + 1])) { out.push({ flag: x, value: a[i + 1] }); i++; }
    else out.push({ flag: x, value: null });
  }
  return out;
}
function keyOf(t) { return t.flag + (t.value !== null && t.value !== undefined ? "=" + t.value : ""); }
function unkey(k) { var i = k.indexOf("="); return i > 0 ? { flag: k.slice(0, i), value: k.slice(i + 1) } : { flag: k, value: null }; }
function wordOf(t) {
  var n = FLAG_NAMES[t.flag];
  if (typeof n === "function") return t.value !== null ? n(t.value) : t.flag;
  if (typeof n === "string") return n + (t.value !== null ? " " + t.value : "");
  return keyOf(t).replace("=", " "); // unknown: verbatim, never dropped
}
// visible flag keys -> plain words, knobs inside their parent when the parent is listed
export function words(keys) {
  var ts = keys.map(unkey), out = [], used = {};
  ts.forEach(function (t, i) {
    if (used[i] || KNOB_OF[t.flag] && keys.some(function (k) { return unkey(k).flag === KNOB_OF[t.flag]; })) return;
    var knobs = [];
    ts.forEach(function (u, j) { if (KNOB_OF[u.flag] === t.flag) { knobs.push(wordOf(u)); used[j] = 1; } });
    out.push(wordOf(t) + (knobs.length ? " (" + knobs.join(", ") + ")" : ""));
  });
  return out;
}
function topicOf(k) {
  var t = unkey(k), f = KNOB_OF[t.flag] || t.flag;
  if (TOPIC[f]) return TOPIC[f];
  return typeof FLAG_NAMES[f] === "string" ? FLAG_NAMES[f] : f;
}
export function visibleKeys(tokens) {
  return tokens.filter(function (t) { return HIDDEN.indexOf(t.flag) < 0; }).map(keyOf);
}

/* ---------- one run ---------- */
var ARM_NOTE = /\[arm (\d+)\/(\d+) of ([^:\]]+): ([^\]]*)\]/;
var ARM_LABEL = /^arm (\d+)\/(\d+) of ([^:]+): (.*)$/;
function sizeOf(runner) {
  if (runner === "lingbot_world2") return "14B model";
  if (runner === "lingbot_world2_1p3b") return "1.3B model";
  if (/fake_runner/.test(runner)) return "fake runner";
  if (/^sana/i.test(runner)) return "SANA-WM";
  if (/matrix_game/i.test(runner)) return "Matrix-Game 3.0";
  return runner ? runner.replace(/^.*\//, "").replace(/\.py$/, "") : "model not recorded";
}
function famText(counts, n) {
  var fams = FAM_ORDER.filter(function (f) { return counts && counts[f]; });
  var extra = counts ? Object.keys(counts).filter(function (f) { return FAM_ORDER.indexOf(f) < 0; }) : [];
  fams = fams.concat(extra);
  if (!fams.length) return typeof n === "number" ? n + (n === 1 ? " task" : " tasks") : "";
  var total = fams.reduce(function (s, f) { return s + counts[f]; }, 0);
  if (fams.length === 1) return total + " " + (FAM_SHORT[fams[0]] || fams[0]) + (total === 1 ? " task" : " tasks");
  if (fams.length === 4) return total + " tasks, all families";
  return total + " tasks: " + fams.map(function (f) { return FAM_SHORT[f] || f; }).join(", ");
}
function pickRow(rows, exp) {
  var rs = rows.filter(function (r) { return r.exp === exp; });
  var sc = rs.filter(function (r) { return r.overall !== null && r.overall !== undefined; });
  return (sc.length ? sc : rs).slice(-1)[0] || null;
}
// one run's facts from whatever exists: its CSV row, Scenes index entry, manifest
export function describe(exp, row, ix, man, now) {
  now = now || Date.now();
  var notes = (row && row.notes) || (man && man.notes) || "";
  var labels = (man && man.labels) || (ix && ix.labels) || [];
  var runner = (man && man.runner) || (row && row.runner) || "";
  var src = (man && man.action_source) || (row && row.action_source) || "";
  var arm = null, argList = null, flagSrc = "";
  var m = ARM_NOTE.exec(notes);
  if (m) arm = { i: +m[1], n: +m[2], group: m[3].trim(), args: m[4] };
  else labels.forEach(function (l) { var x = ARM_LABEL.exec(l); if (x && !arm) arm = { i: +x[1], n: +x[2], group: x[3].trim(), args: x[4] }; });
  if (man && Array.isArray(man.runner_args)) { argList = man.runner_args; flagSrc = "args"; }
  else if (arm) { argList = arm.args; flagSrc = "args"; }
  var tokens = argList !== null ? parseArgs(argList) : [];
  var keys = null;
  if (flagSrc) keys = visibleKeys(tokens);
  else if (/\bno (method )?flags\b/i.test(notes)) { keys = []; flagSrc = "notes"; }
  else if (notes && !/\bcontrol\b|\bvs\b/i.test(notes)) {
    var hit = NOTE_FLAGS.filter(function (p) { return p[0].test(notes); }).map(function (p) { return p[1]; });
    if (hit.length) { keys = hit; flagSrc = "notes"; }
  }
  var scripted = tokens.some(function (t) { return t.flag === "--lingbot-scripted-player"; }) || /scripted player/i.test(notes);
  var driver = scripted ? "scripted moves" : src === "dataset" ? "fixed actions" : (src === "agent" || src === "refined") ? "AI player" : "driver not recorded";
  // cap: manifest, csv, --num-chunks below 30, index label, or the older name/notes markers app.js isCapped reads
  var cap = 0;
  if (man && man.max_chunks > 0) cap = man.max_chunks;
  else if (row && row.max_chunks > 0) cap = row.max_chunks;
  else tokens.forEach(function (t) { if (t.flag === "--num-chunks" && +t.value > 0 && +t.value < 30) cap = +t.value; });
  if (!cap) {
    labels.forEach(function (l) { var x = /^capped[^\d]*(\d+)/i.exec(l); if (x) cap = +x[1]; else if (/^capped/i.test(l) && !cap) cap = -1; });
    var cn = /capped smoke[^\d]*(\d+) chunks/i.exec(notes);
    if (!cap && cn) cap = +cn[1];
    if (!cap && (/^smk\d*-/.test(exp) || /capped smoke/i.test(notes))) cap = -1;
  }
  var test = /fake_runner/.test(runner);
  var counts = null;
  if (man && man.tasks) { counts = {}; man.tasks.forEach(function (t) { counts[t.family] = (counts[t.family] || 0) + 1; }); }
  var n = row && typeof row.n_tasks === "number" ? row.n_tasks : ix && typeof ix.n_tasks === "number" ? ix.n_tasks : null;
  var scored = !!row && row.overall !== null && row.overall !== undefined;
  var status = (row && row.status) || "";
  var stale = status === "running" && !scored && row && row.t && now - row.t > STALE_MS;
  var state, section;
  if (test) { state = "pipeline test"; section = "tests"; }
  else if (cap) { state = "capped " + (cap > 0 ? cap + " chunks" : "") + (scored ? ", scored" : ", not scored"); section = "capped"; }
  else if (scored) { state = "scored" + (row.passes ? ", " + row.passes + (row.passes === 1 ? " pass" : " passes") : ""); section = "scored"; }
  else {
    section = "unscored";
    if (stale) state = "no result";
    else if (status === "running") state = "running";
    else if (status === "failed" || status === "cancelled") state = status;
    else state = "not scored";
  }
  state = state.replace("capped , ", "capped, ");
  var t = (row && row.t) || (ix && Date.parse(ix.generated)) || (man && Date.parse(man.generated)) || 0;
  return {
    exp: exp, size: sizeOf(runner), driver: driver, scripted: scripted, keys: keys, flagSrc: flagSrc,
    words: keys ? words(keys) : null, cap: cap, tasks: famText(counts, n), state: state, section: section, scored: scored,
    t: isFinite(t) ? t : 0, group: arm ? arm.group : "", armI: arm ? arm.i : 0, armN: arm ? arm.n : 0,
    armLabel: "", isControl: false, title: "", short: "", label: "", line: ""
  };
}
function flagsText(info) {
  if (!info.keys) return "flags not recorded";
  return info.words.length ? info.words.join(", ") : "no flags";
}
function facts(info) { return [info.size, info.driver, info.tasks, info.state].filter(Boolean); }

/* ---------- arm groups ---------- */
function minus(a, b) { return a.filter(function (k) { return b.indexOf(k) < 0; }); }
function titleOf(topics) {
  if (!topics.length) return "Repeat test (no flag differs)";
  if (topics.length === 1) return topics[0].charAt(0).toUpperCase() + topics[0].slice(1) + " test";
  var shown = topics.length > 3 ? topics.slice(0, 2) : topics.slice(0, -1);
  var last = topics.length > 3 ? (topics.length - 2) + " more" : topics[topics.length - 1];
  return "Test of " + shown.join(", ") + " and " + last;
}
function sameAll(xs) { return xs.every(function (x) { return x === xs[0]; }); }
function groupState(arms) {
  var st = arms.map(function (a) { return a.state; });
  if (sameAll(st)) return st[0];
  var c = {}; st.forEach(function (s) { var k = s.replace(/, \d+ pass(es)?$/, ""); c[k] = (c[k] || 0) + 1; });
  return Object.keys(c).map(function (k) { return c[k] + " " + k; }).join(", ");
}
function buildGroup(name, arms) {
  arms.sort(function (a, b) { return a.armI - b.armI; });
  var known = arms.filter(function (a) { return a.keys; });
  var setup = known.length ? known[0].keys.filter(function (k) { return known.every(function (a) { return a.keys.indexOf(k) >= 0; }); }) : [];
  var own = {}, fewest = Infinity;
  known.forEach(function (a) { own[a.exp] = minus(a.keys, setup); fewest = Math.min(fewest, own[a.exp].length); });
  var controls = known.filter(function (a) { return own[a.exp].length === fewest; }).map(function (a) { return a.exp; });
  var control = controls[0] || "";
  var topics = [];
  known.forEach(function (a) { own[a.exp].forEach(function (k) { var tp = topicOf(k); if (topics.indexOf(tp) < 0) topics.push(tp); }); });
  var title = titleOf(topics);
  var secs = arms.map(function (a) { return a.section; });
  var section = sameAll(secs) ? secs[0] : secs.indexOf("tests") >= 0 ? "tests" : secs.indexOf("capped") >= 0 ? "capped" : "unscored";
  var common = [].concat(sameAll(arms.map(function (a) { return a.size; })) ? [arms[0].size] : [],
    sameAll(arms.map(function (a) { return a.driver; })) ? [arms[0].driver] : [],
    sameAll(arms.map(function (a) { return a.tasks; })) && arms[0].tasks ? [arms[0].tasks] : []);
  var state = groupState(arms);
  var label = [title].concat(common, [state]).join(" · ") + (setup.length ? " · on top of: " + words(setup).join(", ") : "");
  var g = { name: name, arms: arms, setup: setup, control: control, controls: controls, title: title, label: label, section: section,
    common: common, state: state, setupWords: words(setup),
    t: Math.max.apply(null, arms.map(function (a) { return a.t; }).concat([0])) };
  arms.forEach(function (a) {
    a.title = title;
    if (!a.keys) a.armLabel = "Arm " + a.armI + " (flags not recorded)";
    else if (a.exp === control) { a.armLabel = "Control"; a.isControl = true; }
    else {
      var ctl = known.filter(function (k) { return k.exp === control; })[0];
      a.armLabel = diffLabel(ctl ? ctl.keys : setup, a.keys);
    }
    a.short = a.armLabel + " · " + title;
    a.label = a.short;
    a.head = title + ", arm " + a.armI + " of " + a.armN + ": " + a.armLabel;
    a.rest = facts(a).join(" · ") + " · runs with: " + flagsText(a);
    a.line = a.head + " · " + a.rest;
  });
  return g;
}
// "+ return stop", "+ a, - b", "same flags"
export function diffLabel(base, keys) {
  var add = words(minus(keys, base)), drop = words(minus(base, keys));
  var parts = [];
  if (add.length) parts.push("+ " + add.join(", "));
  if (drop.length) parts.push("- " + drop.join(", "));
  return parts.join("; ") || "same flags";
}
// one line under the Compare cards
export function difference(ctl, trt) {
  if (!ctl || !trt) return "";
  if (!ctl.keys || !trt.keys) return "Difference not recorded: flags of " + (!ctl.keys ? ctl.exp : trt.exp) + " not recorded.";
  var add = words(minus(trt.keys, ctl.keys)), drop = words(minus(ctl.keys, trt.keys));
  var other = [];
  ["size", "driver"].forEach(function (k) { if (ctl[k] !== trt[k]) other.push(ctl[k] + " vs " + trt[k]); });
  if (!add.length && !drop.length && !other.length) return "No recorded difference in flags, model or driver.";
  var parts = [];
  if (add.length) parts.push((drop.length || other.length ? "Treatment adds " : "") + add.join(", "));
  if (drop.length) parts.push("Treatment drops " + drop.join(", "));
  parts = parts.concat(other);
  return (parts.length === 1 && add.length ? "Only difference: " : "Differences: ") + parts.join("; ") + ".";
}

/* ---------- everything ---------- */
// rows: parsed csv rows; runs: index.json runs; mans: {exp: manifest}
export function build(rows, runs, mans, now) {
  rows = rows || []; runs = runs || []; mans = mans || {};
  var ix = {}, names = [], by = {};
  runs.forEach(function (r) { ix[r.exp] = r; if (names.indexOf(r.exp) < 0) names.push(r.exp); });
  rows.forEach(function (r) { if (!r.ref && names.indexOf(r.exp) < 0) names.push(r.exp); });
  names.forEach(function (e) { by[e] = describe(e, pickRow(rows, e), ix[e], mans[e], now); });
  var groups = {}, singles = [];
  names.forEach(function (e) { var i = by[e]; if (i.group) (groups[i.group] = groups[i.group] || []).push(i); else singles.push(i); });
  var G = {};
  Object.keys(groups).forEach(function (k) { G[k] = buildGroup(k, groups[k]); });
  singles.forEach(function (i) {
    i.short = flagsText(i);
    i.label = flagsText(i) + " · " + facts(i).join(" · ");
    i.head = flagsText(i); i.rest = facts(i).join(" · ");
    i.line = i.label;
  });
  return {
    get: function (e) { return by[e] || null; },
    groups: G,
    group: function (e) { var i = by[e]; return i && i.group ? G[i.group] : null; },
    // picker entries for a set of exps: [{section, title, label, group, items: [info]}] newest first, sections in SECTIONS order
    sections: function (exps) {
      var seen = {}, blocks = [];
      exps.forEach(function (e) {
        var i = by[e]; if (!i) return;
        if (i.group) {
          if (seen[i.group]) { seen[i.group].items.push(i); return; }
          var g = G[i.group];
          seen[i.group] = { section: g.section, label: g.label, group: g.name, t: g.t, items: [i] };
          blocks.push(seen[i.group]);
        } else blocks.push({ section: i.section, label: "", group: "", t: i.t, items: [i] });
      });
      blocks.forEach(function (b) { b.items.sort(function (x, y) { return x.armI - y.armI; }); });
      return SECTIONS.map(function (s) {
        var bs = blocks.filter(function (b) { return b.section === s[0]; }).sort(function (a, b) { return b.t - a.t; });
        return { key: s[0], title: s[1], blocks: bs };
      }).filter(function (s) { return s.blocks.length; });
    },
    // <select> model: [{label, options: [{value, text}]}]; a header entry has no options. Capped smoke and
    // pipeline tests fold into one "show more" option unless showAll or the current run is one of them.
    options: function (exps, current, showAll) {
      var out = [], folded = 0, self = this;
      self.sections(exps).forEach(function (s) {
        var lazy = (s.key === "capped" || s.key === "tests") && !showAll &&
          !s.blocks.some(function (b) { return b.items.some(function (i) { return i.exp === current; }); });
        if (lazy) { s.blocks.forEach(function (b) { folded += b.items.length; }); return; }
        out.push({ label: s.title.toUpperCase(), options: [] });
        var singles = [];
        s.blocks.forEach(function (b) {
          if (b.group) out.push({ label: b.label, options: b.items.map(function (i) { return { value: i.exp, text: i.armLabel + "  (" + i.exp + ")" }; }) });
          else singles.push({ value: b.items[0].exp, text: b.items[0].label + "  (" + b.items[0].exp + ")" });
        });
        if (singles.length) out.push({ label: "Single runs", options: singles });
      });
      if (folded) out.push({ label: "", options: [{ value: MORE, text: "Show " + folded + " capped smoke and pipeline test run" + (folded === 1 ? "" : "s") }] });
      return out;
    }
  };
}
