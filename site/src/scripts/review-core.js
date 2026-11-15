// Blind review page, pure parts: pair list, seeded sides and order, sign test, Cohen's kappa, export rows.
// No DOM here, so review.check.mjs can test it under node. review.js renders.

import { clipMap } from "./clips.js";

export const PAGE_VERSION = "review-2";

// Pair sets. Within a set, control and treatment share seed and fixed moves, except closed-loop sets, where the
// AI player picks the moves for each clip. Arms checked against results/experiments.csv notes and each
// manifest's runner_args (Nov 15 2026).
// skip: tasks left out of voting. The yaw servo only acts on turns, so walking-only GC tasks measure noise (fixed
// moves) or the AI player (closed loop), not the servo. attention: of those, tasks whose two published clips are
// byte-identical (sha1 of the release assets, Nov 15 2026), shown as ordinary trials with the expected answer
// "no difference" and tallied apart. stksv-gc GC005 differs between arms, so it is skipped, not a check.
const WALK_ONLY = ["GC005", "GC016", "GC002", "GC025", "GC045"];
export const SETS = [
  { id: "stk-dev-s0", group: "stack", ctl: "stk14-fx-dev-v1-a1", trt: "stk14-fx-dev-v1-a2", label: "dev tasks, seed 0" },
  { id: "stk-dev-s1", group: "stack", ctl: "stk14-fx-dev-v1-a3", trt: "stk14-fx-dev-v1-a4", label: "dev tasks, seed 1" },
  { id: "stk-dev2", group: "stack", ctl: "stk14-fx-dev2-v1-a1", trt: "stk14-fx-dev2-v1-a2", label: "dev2 tasks, seed 0" },
  { id: "sv-gc", group: "servo", ctl: "svgc14-fx-v1-a1", trt: "svgc14-fx-v1-a2", label: "caption prompt and turn calibration in both", skip: WALK_ONLY, attention: ["GC005", "GC016", "GC025", "GC045"] },
  { id: "stksv-gc", group: "servo", ctl: "stksv14-fx-gc-v1-a1", trt: "stksv14-fx-gc-v1-a2", label: "stack in both", skip: WALK_ONLY, attention: ["GC002", "GC016", "GC025", "GC045"] },
  { id: "stksv-cl", group: "servo-cl", ctl: "stksv14-cl-gc-v1-a1", trt: "stksv14-cl-gc-v1-a2", label: "stack in both, AI player", skip: WALK_ONLY }
];
// The same file can sit in two sets: stk14-fx-dev-v1-a2 (stack, seed 0) GC005/016/031/033/038 equal
// stksv14-fx-gc-v1-a1 (servo control) byte for byte. The reveal says so when both groups are in a selection.
export const SHARED_CLIPS = { sets: ["stk-dev-s0", "stksv-gc"], tasks: ["GC005", "GC016", "GC031", "GC033", "GC038"] };
export const GROUPS = {
  stack: { name: "Stack vs no flags", short: "+ stack", what: "Same seed and same fixed moves in both clips.", treat: "stack: turn calibration, caption prompt, insight director, IF slow translation, keep-first 10, attention window 22", control: "no flags" },
  servo: { name: "Yaw servo vs control (GC)", short: "+ yaw servo", what: "Same seed and same fixed moves in both clips.", treat: "yaw servo on", control: "yaw servo off" },
  "servo-cl": { name: "Yaw servo vs control (GC, closed loop)", short: "+ yaw servo", what: "Closed loop: the AI player chose the moves for each clip, so the two clips can follow different moves and run for different lengths. A clip that ends holds its last frame under a \"Clip ended\" label; judge stability only over the part both clips play.", treat: "yaw servo on", control: "yaw servo off", closed: true }
};
export const FAMS = ["gc", "if", "insight", "outsight"];

/* ---------- seeded randomness ---------- */
// cyrb53: a 53-bit string hash, good spread for short keys
export function hash(str) {
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 2654435761); h2 = Math.imul(h2 ^ c, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return 4294967296 * (2097151 & h2) + (h1 >>> 0);
}
export function rng(seed) { // mulberry32
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function norm(reviewer) { return String(reviewer || "").trim().toLowerCase(); }
// the side seed: reviewer name, plus the round once "Clear my votes and start over" has been used
export function sideSeed(reviewer, round) { return norm(reviewer) + (round ? "#" + round : ""); }
// which side the treatment clip is on, per pair. Balanced within each group and family: the stratum's pairs are put in
// a seeded order and alternate sides, so a stratum of n pairs has floor(n/2) or ceil(n/2) on the left.
export function assignSides(seed, pairs) {
  const strata = {}, out = {};
  pairs.forEach((p) => { (strata[p.group + "|" + p.family] ||= []).push(p.id); });
  Object.keys(strata).sort().forEach((k) => {
    const ids = shuffled(strata[k].slice().sort(), "side|" + seed + "|" + k), flip = hash("flip|" + seed + "|" + k) % 2;
    ids.forEach((id, i) => { out[id] = (i + flip) % 2 ? "right" : "left"; });
  });
  return out;
}
// trial order: a Fisher-Yates shuffle seeded by reviewer and the chosen group and family
export function shuffled(items, seedKey) {
  const r = rng(hash("order|" + seedKey) % 4294967296), a = items.slice();
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); const t = a[i]; a[i] = a[j]; a[j] = t; }
  return a;
}

/* ---------- pairs from the manifests ---------- */
// mans: {exp: manifest}. Returns {pairs, dropped: [{set, why}]}. A pair needs both clips; a set needs both manifests.
export function buildPairs(mans) {
  const pairs = [], dropped = [];
  SETS.forEach((s) => {
    const a = mans[s.ctl], b = mans[s.trt];
    if (!a || !b) { dropped.push({ set: s.id, group: s.group, why: "manifest missing: " + [!a ? s.ctl : null, !b ? s.trt : null].filter(Boolean).join(", ") }); return; }
    const ca = clipMap(a), cb = clipMap(b);
    Object.keys(ca).sort().forEach((task) => {
      if (!cb[task]) return;
      const attention = (s.attention || []).indexOf(task) >= 0;
      if (!attention && (s.skip || []).indexOf(task) >= 0) return;
      pairs.push({ id: s.id + ":" + task, set: s.id, group: s.group, task, family: ca[task].family || cb[task].family || "",
        attention, ctl: { exp: s.ctl, video: ca[task].video, poster: ca[task].poster || "" }, trt: { exp: s.trt, video: cb[task].video, poster: cb[task].poster || "" } });
    });
  });
  return { pairs, dropped };
}

/* ---------- votes ---------- */
// a vote is the side picked ("left" | "right" | "none"); pref turns it into the arm preferred
export function pref(side, trtSide) { if (side === "none") return "none"; if (side !== "left" && side !== "right") return ""; return side === trtSide ? "treatment" : "control"; }

/* ---------- statistics ---------- */
// exact two-sided sign test: k of n untied preferences went one way, p = P(|X - n/2| >= |k - n/2|), X ~ Bin(n, 1/2)
export function signTest(k, n) {
  if (!n) return 1;
  const lo = Math.min(k, n - k);
  let tail = 0, c = 1; // c = C(n, i)
  for (let i = 0; i <= lo; i++) { tail += c; c = c * (n - i) / (i + 1); }
  // tail / 2^n, done in logs so n up to a few thousand stays finite
  const p = 2 * Math.exp(Math.log(tail) - n * Math.LN2);
  return Math.min(1, p);
}
// Cohen's kappa for two raters over the same items. a, b: arrays of category labels of equal length.
export function kappa(a, b) {
  const n = a.length; if (!n) return { kappa: null, po: null, pe: null, n: 0 };
  const cats = Array.from(new Set(a.concat(b))), ca = {}, cb = {};
  let agree = 0;
  for (let i = 0; i < n; i++) { if (a[i] === b[i]) agree++; ca[a[i]] = (ca[a[i]] || 0) + 1; cb[b[i]] = (cb[b[i]] || 0) + 1; }
  const po = agree / n;
  let pe = 0; cats.forEach((c) => { pe += ((ca[c] || 0) / n) * ((cb[c] || 0) / n); });
  return { kappa: pe === 1 ? (po === 1 ? 1 : null) : (po - pe) / (1 - pe), po, pe, n };
}
// counts per key: {treatment, control, none, n, p}
export function tally(votes, q) {
  const out = { treatment: 0, control: 0, none: 0 };
  votes.forEach((v) => { const p = v[q]; if (p && out[p] !== undefined) out[p]++; });
  out.n = out.treatment + out.control + out.none;
  out.p = signTest(out.treatment, out.treatment + out.control);
  return out;
}

/* ---------- export / import ---------- */
export const CSV_COLS = ["reviewer", "round", "pair_id", "task", "family", "group", "set", "attention", "treatment_side", "follow", "follow_pref", "stable", "stable_pref", "note", "first_voted", "last_voted", "revealed_at", "reveal", "page_version", "manifests"];
function q(v) { const s = v === null || v === undefined ? "" : String(v); return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
export function toCSV(doc) {
  const mv = Object.keys(doc.manifests || {}).sort().map((k) => k + "@" + doc.manifests[k]).join(" ");
  const lines = [CSV_COLS.join(",")];
  doc.votes.forEach((v) => { lines.push(CSV_COLS.map((c) => q(c === "page_version" ? doc.page_version : c === "manifests" ? mv : c === "reviewer" ? doc.reviewer : c === "round" ? (doc.round || 0) : c === "reveal" ? (doc.reveal || "at_end") : v[c])).join(",")); });
  return lines.join("\n") + "\n";
}
export function parseCSV(text) {
  const rows = []; let row = [], f = "", inq = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inq) { if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else inq = false; } else f += c; continue; }
    if (c === '"') inq = true; else if (c === ",") { row.push(f); f = ""; } else if (c === "\n") { row.push(f); rows.push(row); row = []; f = ""; } else if (c !== "\r") f += c;
  }
  if (f || row.length) { row.push(f); rows.push(row); }
  return rows;
}
// a second reviewer's file, JSON or CSV, to {reviewer, votes: [{pair_id, follow_pref, stable_pref}]}
export function readResults(text) {
  const s = String(text || "").trim();
  if (s[0] === "{") {
    const d = JSON.parse(s);
    if (!d || !Array.isArray(d.votes)) throw new Error("not a review results file");
    return { reviewer: d.reviewer || "", votes: d.votes };
  }
  const rows = parseCSV(s), head = rows[0] || [];
  if (head.indexOf("pair_id") < 0 || head.indexOf("follow_pref") < 0) throw new Error("not a review results file");
  const votes = rows.slice(1).filter((r) => r.length > 1).map((r) => { const o = {}; head.forEach((h, j) => (o[h] = r[j] === undefined ? "" : r[j])); return o; });
  return { reviewer: (votes[0] && votes[0].reviewer) || "", votes };
}
// per-trial agreement between two reviewers on question key q, over pairs both answered
export function agreement(mine, theirs, q) {
  const by = {}; theirs.forEach((v) => { if (v.pair_id && v[q]) by[v.pair_id] = v; });
  const rows = [];
  mine.forEach((v) => { if (v[q] && by[v.pair_id]) rows.push({ pair_id: v.pair_id, task: v.task, group: v.group, family: v.family, a: v[q], b: by[v.pair_id][q] }); });
  const k = kappa(rows.map((r) => r.a), rows.map((r) => r.b));
  return { rows, kappa: k.kappa, po: k.po, n: k.n };
}
