// Self-check for review-core.js: node src/scripts/review.check.mjs (from site/). Runs in CI with no browser.
// The blinding check against the built page is review.browser.mjs (needs Playwright).
import { readFileSync, readdirSync } from "node:fs";
import assert from "node:assert/strict";
import * as C from "./review-core.js";

// real pair ids are balanced too
const mans = {};
const mdir = new URL("../../../results/media/", import.meta.url);
for (const f of readdirSync(mdir)) if (f !== "index.json" && f.endsWith(".json")) { const m = JSON.parse(readFileSync(new URL(f, mdir), "utf8")); mans[m.exp] = m; }
const { pairs, dropped } = C.buildPairs(mans);
// seeded sides: deterministic, case-insensitive, balanced within every group and family, new sides per round
const strata = {}; pairs.forEach((p) => (strata[p.group + "|" + p.family] ||= []).push(p.id));
for (const r of ["AB", "jp", "Reviewer 2", "alice", "x"]) {
  const s1 = C.assignSides(C.sideSeed(r, 0), pairs);
  assert.deepEqual(s1, C.assignSides(C.sideSeed(" " + r.toUpperCase() + " ", 0), pairs), "sides ignore case and outer spaces");
  assert.deepEqual(s1, C.assignSides(C.sideSeed(r, 0), pairs.slice().reverse()), "sides do not depend on list order");
  assert.equal(Object.keys(s1).length, pairs.length);
  for (const [k, ids] of Object.entries(strata)) {
    const left = ids.filter((id) => s1[id] === "left").length;
    assert.ok(left === Math.floor(ids.length / 2) || left === Math.ceil(ids.length / 2), r + " " + k + ": " + left + " of " + ids.length + " left");
  }
  const s2 = C.assignSides(C.sideSeed(r, 1), pairs);
  const moved = pairs.filter((p) => s1[p.id] !== s2[p.id]).length;
  assert.ok(moved > pairs.length * 0.3 && moved < pairs.length * 0.7, r + ": a new round redraws sides (" + moved + " moved)");
}
// over many reviewers, a given pair's treatment is left about half the time, and two reviewers' sides are independent
let leftN = 0, same = 0; const N = 2000, pid = pairs[0].id, pid2 = pairs[pairs.length - 1].id;
for (let i = 0; i < N; i++) { const a1 = C.assignSides("r" + i, pairs), b1 = C.assignSides("q" + i, pairs); if (a1[pid] === "left") leftN++; if (a1[pid2] === b1[pid2]) same++; }
assert.ok(Math.abs(leftN / N - 0.5) < 0.04, "pair side balance over reviewers: " + leftN + "/" + N);
assert.ok(Math.abs(same / N - 0.5) < 0.04, "two reviewers' sides are independent: " + same + "/" + N);
// seeded order: deterministic, a permutation, and not the identity
const ids = pairs.map((p) => p.id);
const o1 = C.shuffled(ids, "ab|all|all").join(), o2 = C.shuffled(ids, "ab|all|all").join();
assert.equal(o1, o2, "same seed, same order");
assert.deepEqual(C.shuffled(ids, "ab|all|all").slice().sort(), ids.slice().sort(), "order is a permutation");
assert.notEqual(o1, ids.join(), "order is shuffled");
assert.notEqual(o1, C.shuffled(ids, "cd|all|all").join(), "another reviewer, another order");
// position balance of the shuffle: item 0 lands in each half about equally often
let firstHalf = 0; for (let s = 0; s < 4000; s++) if (C.shuffled([0, 1, 2, 3, 4, 5, 6, 7], "s" + s).indexOf(0) < 4) firstHalf++;
assert.ok(Math.abs(firstHalf / 4000 - 0.5) < 0.03, "shuffle position balance " + firstHalf);

// sign test: exact two-sided binomial p, checked against values computed by hand / R binom.test
const near = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-9, msg + ": " + a + " vs " + b);
near(C.signTest(0, 0), 1, "n 0");
near(C.signTest(5, 10), 1, "5 of 10");
near(C.signTest(10, 10), 2 / 1024, "10 of 10");
near(C.signTest(0, 10), 2 / 1024, "0 of 10");
near(C.signTest(9, 10), 22 / 1024, "9 of 10"); // 2 * (1 + 10) / 1024 = 0.021484375
near(C.signTest(8, 10), 0.109375, "8 of 10"); // 2 * (1 + 10 + 45) / 1024
near(C.signTest(3, 12), 598 / 4096, "3 of 12"); // 2 * (1 + 12 + 66 + 220) / 4096 = 0.14599609375
near(C.signTest(1, 1), 1, "1 of 1");
near(C.signTest(6, 6), 0.03125, "6 of 6");
assert.ok(Math.abs(C.signTest(60, 100) - 0.0568879336) < 1e-9, "60 of 100 (R binom.test 0.05688793): " + C.signTest(60, 100));
assert.ok(C.signTest(700, 1000) > 0 && C.signTest(700, 1000) < 1e-30, "large n stays finite");

// Cohen's kappa: 2x2 table from Cohen (1960)-style textbook example: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> po 0.7, pe 0.5, kappa 0.4
const a = [], b = [];
const add = (x, y, n) => { for (let i = 0; i < n; i++) { a.push(x); b.push(y); } };
add("yes", "yes", 20); add("yes", "no", 5); add("no", "yes", 10); add("no", "no", 15);
const k = C.kappa(a, b);
near(k.po, 0.7, "po"); near(k.pe, 0.5, "pe"); near(k.kappa, 0.4, "kappa");
// 3x3: treatment / control / none, diagonal 10, 8, 4 of 30; marginals give pe = (12*13 + 11*10 + 7*7) / 900
const a3 = [], b3 = [];
const add3 = (x, y, n) => { for (let i = 0; i < n; i++) { a3.push(x); b3.push(y); } };
add3("treatment", "treatment", 10); add3("treatment", "control", 1); add3("treatment", "none", 1);
add3("control", "treatment", 2); add3("control", "control", 8); add3("control", "none", 1);
add3("none", "treatment", 1); add3("none", "control", 1); add3("none", "none", 5);
const k3 = C.kappa(a3, b3), pe3 = (12 * 13 + 11 * 10 + 7 * 7) / 900, po3 = 23 / 30;
near(k3.kappa, (po3 - pe3) / (1 - pe3), "3x3 kappa");
assert.equal(C.kappa(["x", "x"], ["x", "x"]).kappa, 1, "perfect agreement on one category");

// pairs from the committed manifests
const byGroup = {}; pairs.forEach((p) => { const g = (byGroup[p.group] ||= {}); g[p.family] = (g[p.family] || 0) + 1; });
assert.equal(pairs.filter((p) => p.group === "stack").length, 72, "stack: 3 x 24 pairs");
assert.ok(pairs.filter((p) => p.attention).every((p) => p.group === "servo" && p.family === "gc"), "attention checks are fixed-move servo GC trials");
assert.deepEqual(pairs.filter((p) => p.attention).map((p) => p.id).sort(), ["stksv-gc:GC002", "stksv-gc:GC016", "stksv-gc:GC025", "stksv-gc:GC045", "sv-gc:GC005", "sv-gc:GC016", "sv-gc:GC025", "sv-gc:GC045"], "eight attention checks, every byte-identical walking-only pair");
assert.ok(!pairs.some((p) => p.group.startsWith("servo") && !p.attention && ["GC005", "GC016", "GC002", "GC025", "GC045"].includes(p.task)), "walking-only tasks are out of servo voting, closed loop included");
assert.deepEqual(pairs.filter((p) => p.group === "servo-cl").map((p) => p.task), ["GC031", "GC033", "GC036", "GC038"], "closed-loop servo trials");
assert.equal(pairs.filter((p) => p.group === "servo" && !p.attention).length, 12, "servo: 5 + 7 voting trials");
assert.ok(pairs.every((p) => p.ctl.video && p.trt.video && p.ctl.exp !== p.trt.exp), "both clips exist");
assert.equal(new Set(pairs.map((p) => p.id)).size, pairs.length, "pair ids unique");
assert.deepEqual(C.buildPairs({}).dropped.length, C.SETS.length, "every set dropped without manifests");

// export round trip
const doc = { page_version: C.PAGE_VERSION, reviewer: "AB", round: 2, manifests: { x: "2026" }, votes: [
  { pair_id: "s:GC1", task: "GC1", family: "gc", group: "servo", set: "s", attention: false, treatment_side: "left", follow: "left", follow_pref: "treatment", stable: "", stable_pref: "", note: 'a, "b"\nc', first_voted: "t0", last_voted: "t1" }] };
const back = C.readResults(C.toCSV(doc));
assert.equal(back.reviewer, "AB"); assert.equal(back.votes[0].round, "2"); assert.equal(back.votes[0].note, 'a, "b"\nc'); assert.equal(back.votes[0].follow_pref, "treatment");
assert.equal(C.readResults(JSON.stringify(doc)).votes.length, 1);
assert.equal(C.pref("left", "left"), "treatment"); assert.equal(C.pref("right", "left"), "control"); assert.equal(C.pref("none", "left"), "none"); assert.equal(C.pref("", "left"), "");
const ag = C.agreement([{ pair_id: "p1", follow_pref: "treatment" }, { pair_id: "p2", follow_pref: "none" }], [{ pair_id: "p1", follow_pref: "treatment" }, { pair_id: "p2", follow_pref: "control" }], "follow_pref");
assert.equal(ag.n, 2); near(ag.po, 0.5, "agreement");

if (process.argv.includes("--print")) { console.log(JSON.stringify(byGroup)); console.log(dropped); }
console.log("review.check: ok (" + pairs.length + " pairs: " + Object.entries(byGroup).map(([g, f]) => g + " " + JSON.stringify(f)).join("; ") + "; " + dropped.length + " sets dropped)");
