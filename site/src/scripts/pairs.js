// Control/treatment clip pairs, derived from the Scenes index and the per-run manifests. Pure: no DOM, no fetch.
// Used by pairsview.js (the Pairs section), checked by pairs.check.mjs against results/media.
// A pair is one task from two runs that differ only by added flags: same runner, model size, driver, player,
// cap and seed. Control candidates are the treatment's own arm group plus EXP-aN runs named in its notes;
// per task the candidate with the fewest flags that has the clip wins (ties: same group, more shared clips, notes order). No scores are read or computed here.
import { words, visibleKeys, parseArgs } from "./runinfo.js";
import { playableUrl, clipMap } from "./clips.js";
export { playableUrl };

export var SECTIONS = [
  ["fixed", "Fixed actions"],
  ["agent", "AI player (actions differ)"],
  ["scripted", "Scripted moves"],
  ["capped", "Capped"],
  ["repeats", "Seed repeats"]
];
var NAMED = /\b[a-z0-9]+(?:-[a-z0-9]+)*-a\d+\b/g;

function sorted(a) { return a.slice().sort(); }
function subsetStrict(a, b) { return a.length < b.length && a.every(function (k) { return b.indexOf(k) >= 0; }); }
function sameSet(a, b) { return a.length === b.length && a.every(function (k) { return b.indexOf(k) >= 0; }); }
function minus(a, b) { return a.filter(function (k) { return b.indexOf(k) < 0; }); }

// one run's pairing facts, or null when it cannot pair (no manifest, no playable clip, flags unknown)
export function runFacts(exp, man, info, origin) {
  if (!man || !info || !info.keys) return null;
  var tasks = clipMap(man, function (u) { return playableUrl(u, origin); });
  if (!Object.keys(tasks).length) return null;
  var seed = "0", keys = [];
  // the manifest's args are authoritative; info.keys covers runs whose flags come from notes
  var ks = Array.isArray(man.runner_args) ? visibleKeys(parseArgs(man.runner_args)) : info.keys;
  ks.forEach(function (k) { if (/^--seed(=|$)/.test(k)) seed = k.indexOf("=") > 0 ? k.slice(k.indexOf("=") + 1) : "0"; else keys.push(k); });
  var named = [];
  ((man.notes || "") + "").replace(NAMED, function (m) { if (m !== exp && named.indexOf(m) < 0) named.push(m); return m; });
  return {
    exp: exp, keys: keys, seed: seed, group: info.group || "", armI: info.armI || 0,
    runner: man.runner || "", size: info.size, driver: info.driver, player: man.player_model || "",
    // the cap value itself, not just whether one exists: a 10-chunk run never pairs with a 20-chunk one
    cap: info.cap ? String(info.cap) : 0, capN: info.cap > 0 ? info.cap : 0, sha: man.git_sha || "", tasks: tasks, named: named
  };
}
function identity(f) { return [f.runner, f.size, f.driver, f.player, f.cap, f.seed].join("|"); }
function sectionOf(f) { return f.cap ? "capped" : f.driver === "AI player" ? "agent" : f.driver === "scripted moves" ? "scripted" : "fixed"; }

function cover(c, t) { return Object.keys(t.tasks).filter(function (k) { return c.tasks[k]; }).length; }
// candidates in preference order: fewest flags, then same group, then task coverage, then notes order
function candidates(t, all, by) {
  var out = all.filter(function (c) {
    if (c === t) return false;
    var linked = c.group && c.group === t.group || t.named.indexOf(c.exp) >= 0;
    return linked && identity(c) === identity(t) && subsetStrict(c.keys, t.keys);
  });
  out.sort(function (a, b) {
    if (a.keys.length !== b.keys.length) return a.keys.length - b.keys.length;
    var ga = a.group === t.group ? 0 : 1, gb = b.group === t.group ? 0 : 1;
    if (ga !== gb) return ga - gb;
    // then the candidate that covers more of the treatment's tasks, so one control serves most pairs
    var ca = cover(a, t), cb = cover(b, t);
    if (ca !== cb) return cb - ca;
    var na = t.named.indexOf(a.exp), nb = t.named.indexOf(b.exp);
    if (na !== nb) return (na < 0 ? 1e9 : na) - (nb < 0 ? 1e9 : nb);
    return a.armI - b.armI;
  });
  return out;
}
// a stable, readable URL key from the raw flags: "yaw-servo_on_caption-prompt+turn-cal_fixed"
function short(k) { return k.replace(/^--(lingbot-)?/, ""); }
var DRIVER_KEY = { "fixed actions": "fixed", "AI player": "agent", "scripted moves": "scripted" };
function cmpKey(added, base, f) {
  return sorted(added.map(short)).join("+") + "_on_" + (sorted(base.map(short)).join("+") || "none") + "_" + (DRIVER_KEY[f.driver] || "other") + (f.cap ? "_capped" : "");
}
// index: results/media/index.json; mans: {exp: manifest}; RI: runinfo.build(...) result; opts.origin for same-origin clips
export function derivePairs(index, mans, RI, opts) {
  opts = opts || {};
  var runs = (index && index.runs) || [];
  var all = [], by = {};
  runs.forEach(function (r) {
    var f = runFacts(r.exp, mans[r.exp], RI && RI.get(r.exp), opts.origin);
    if (f && !by[f.exp]) { all.push(f); by[f.exp] = f; }
  });
  var comps = {}, order = [], byTriple = {}, alt = {};
  function comp(key, f, added, base) {
    if (!comps[key]) {
      var addW = words(added), baseW = words(base);
      var label = "+ " + addW.join(", ") + " · on " + (baseW.length ? baseW.join(", ") : "no flags");
      if (f.driver === "AI player") label += " · AI player chose moves in each arm: actions differ";
      else if (f.driver === "scripted moves") label += " · scripted moves";
      if (f.cap) label += " · capped" + (f.capN ? " " + f.capN + " chunks" : "");
      comps[key] = { key: key, label: label,
        added: addW, base: baseW, driver: f.driver, capped: !!f.cap, section: sectionOf(f), pairs: [], runs: [] };
      order.push(key);
    }
    return comps[key];
  }
  all.forEach(function (t) {
    var cs = candidates(t, all, by);
    if (!cs.length) return;
    Object.keys(t.tasks).sort().forEach(function (task) {
      var have = cs.filter(function (x) { return x.tasks[task]; }), c = have[0];
      if (!c) return;
      // other valid controls for this task: old links that name one get an accurate note, not "not a pair"
      have.slice(1).forEach(function (x) { alt[task + "|" + x.exp + "|" + t.exp] = c.exp; });
      var added = minus(t.keys, c.keys);
      var k = cmpKey(added, c.keys, t);
      var C = comp(k, t, added, c.keys);
      var p = { task: task, family: t.tasks[task].family || c.tasks[task].family || "", ctl: c.exp, trt: t.exp, seed: t.seed,
        cross: c.group !== t.group || !t.group, shaDiff: !!(c.sha && t.sha && c.sha !== t.sha) };
      C.pairs.push(p);
      [c.exp, t.exp].forEach(function (e) { if (C.runs.indexOf(e) < 0) C.runs.push(e); });
      byTriple[task + "|" + c.exp + "|" + t.exp] = C.key;
    });
  });
  // seed repeats: same group, same flags and identity apart from the seed
  var repeats = [];
  var seenR = {};
  all.forEach(function (a) {
    all.forEach(function (b) {
      if (a === b || !a.group || a.group !== b.group || a.seed === b.seed || !sameSet(a.keys, b.keys)) return;
      if (identity(Object.assign({}, a, { seed: "" })) !== identity(Object.assign({}, b, { seed: "" }))) return;
      if (+a.seed > +b.seed || a.seed === b.seed) return;
      var id = a.exp + "|" + b.exp; if (seenR[id]) return; seenR[id] = 1;
      var fw = words(a.keys);
      var R = { key: "repeat_" + a.exp + "_" + b.exp, label: "Same flags, seed " + a.seed + " vs seed " + b.seed + " (no method difference) · " + (fw.length ? fw.join(", ") : "no flags") + " · " + a.group,
        added: [], base: fw, driver: a.driver, capped: !!a.cap, section: "repeats", repeat: true, pairs: [], runs: [a.exp, b.exp] };
      Object.keys(a.tasks).sort().forEach(function (task) {
        if (!b.tasks[task]) return;
        R.pairs.push({ task: task, family: a.tasks[task].family || "", ctl: a.exp, trt: b.exp, seed: a.seed + "/" + b.seed, cross: false, shaDiff: !!(a.sha && b.sha && a.sha !== b.sha) });
        byTriple[task + "|" + a.exp + "|" + b.exp] = R.key;
      });
      if (R.pairs.length) repeats.push(R);
    });
  });
  var comparisons = order.map(function (k) { return comps[k]; });
  // keys must be unique: suffix a counter on a slug collision
  var used = {};
  comparisons.concat(repeats).forEach(function (c) {
    var base = c.key, n = 2; while (used[c.key]) c.key = base + "-" + n++;
    used[c.key] = 1;
    c.pairs.forEach(function (p) { byTriple[p.task + "|" + p.ctl + "|" + p.trt] = c.key; });
  });
  comparisons.sort(function (a, b) { return b.pairs.length - a.pairs.length || (a.label < b.label ? -1 : 1); });
  Object.keys(byTriple).forEach(function (k) { delete alt[k]; });
  return { comparisons: comparisons, repeats: repeats, byTriple: byTriple, alt: alt, runs: all.map(function (f) { return f.exp; }) };
}

// every comparison and repeat by key
export function findComparison(D, key) {
  return D.comparisons.concat(D.repeats).filter(function (c) { return c.key === key; })[0] || null;
}
// the pairs of a comparison after the family and seed filters
export function filterPairs(c, fam, seed) {
  return (c ? c.pairs : []).filter(function (p) { return (!fam || p.family === fam) && (!seed || p.seed === seed); });
}
export function seedsOf(c) {
  var s = []; (c ? c.pairs : []).forEach(function (p) { if (s.indexOf(p.seed) < 0) s.push(p.seed); });
  return s.sort();
}
// a pair's id inside a filtered list: the task, plus the control when the task appears more than once
export function pairId(list, p) {
  var n = list.filter(function (x) { return x.task === p.task; }).length;
  return n > 1 ? p.task + "~" + p.ctl : p.task;
}
export function pairById(list, id) {
  if (!id) return -1;
  var parts = id.split("~");
  for (var i = 0; i < list.length; i++) if (list[i].task === parts[0] && (!parts[1] || list[i].ctl === parts[1])) return i;
  return -1;
}
// URL state <-> query: ?cmp=KEY&fam=&seed=&pair=TASK
export function readState(search) {
  var q = new URLSearchParams(search || "");
  return { cmp: q.get("cmp") || "", fam: q.get("fam") || "", seed: q.get("seed") || "", pair: q.get("pair") || "" };
}
export function writeState(search, st) {
  var q = new URLSearchParams(search || "");
  ["compare", "a", "b", "c"].forEach(function (k) { q.delete(k); });
  [["cmp", st.cmp], ["fam", st.fam], ["seed", st.seed], ["pair", st.pair]].forEach(function (kv) { if (kv[1]) q.set(kv[0], kv[1]); else q.delete(kv[0]); });
  return q.toString();
}
// a triple that is a valid control/treatment pair, but the pair list uses another control for that task: that control, else ""
export function altControl(D, task, b, c) { return (D.alt && D.alt[task + "|" + b + "|" + c]) || ""; }
// the hand-pick note for an old link that is not in the pair list
export function legacyNote(D, task, b, c) {
  var alt = altControl(D, task, b, c);
  return alt ? "A valid control for this treatment (same settings and seed, fewer flags). The pair list uses " + alt + " for " + task + "."
    : "Not a derived control/treatment pair: these runs differ in more than added flags, or are not linked as control and treatment.";
}
// an old ?compare=TASK&b=C&c=T link: the derived comparison holding that triple, or null for hand-pick mode
export function mapLegacy(D, task, b, c) {
  var k = D.byTriple[task + "|" + b + "|" + c];
  return k ? { cmp: k, fam: "", seed: "", task: task, ctl: b, trt: c } : null;
}
