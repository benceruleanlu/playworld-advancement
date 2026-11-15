// Self-check for review-core.js: node src/scripts/review.check.mjs (from site/). Runs in CI with no browser.
// The blinding check against the built page is review.browser.mjs (needs Playwright).
import { readFileSync, readdirSync } from "node:fs";
import assert from "node:assert/strict";
import * as C from "./review-core.js";

// seeded sides: deterministic, and balanced over many trials
assert.equal(C.treatmentSide("AB", "stk-dev-s0:GC005"), C.treatmentSide("ab ", "stk-dev-s0:GC005"), "side ignores case and outer spaces");
for (const r of ["AB", "jp", "Reviewer 2"]) {
  let left = 0; const N = 10000;
  for (let i = 0; i < N; i++) { const s = C.treatmentSide(r, "set:" + i); assert.equal(s, C.treatmentSide(r, "set:" + i)); if (s === "left") left++; }
  assert.ok(Math.abs(left / N - 0.5) < 0.02, r + ": treatment left in " + left + " of " + N);
}
// two reviewers get different side assignments (not the same bit for every pair)
let same = 0; for (let i = 0; i < 1000; i++) if (C.treatmentSide("AB", "p" + i) === C.treatmentSide("CD", "p" + i)) same++;
assert.ok(same > 430 && same < 570, "two reviewers' sides are independent: " + same + "/1000 equal");
// real pair ids are balanced too
const mans = {};
const mdir = new URL("../../../results/media/", import.meta.url);
for (const f of readdirSync(mdir)) if (f !== "index.json" && f.endsWith(".json")) { const m = JSON.parse(readFileSync(new URL(f, mdir), "utf8")); mans[m.exp] = m; }
const { pairs, dropped } = C.buildPairs(mans);
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
assert.equal(pairs.filter((p) => p.attention).length, 3, "three attention checks");
assert.ok(!pairs.some((p) => p.group === "servo" && !p.attention && ["GC005", "GC016", "GC002", "GC025", "GC045"].includes(p.task)), "walking-only tasks are out of servo voting");
assert.ok(pairs.every((p) => p.ctl.video && p.trt.video && p.ctl.exp !== p.trt.exp), "both clips exist");
assert.equal(new Set(pairs.map((p) => p.id)).size, pairs.length, "pair ids unique");
assert.deepEqual(C.buildPairs({}).dropped.length, C.SETS.length, "every set dropped without manifests");

// export round trip
const doc = { page_version: C.PAGE_VERSION, reviewer: "AB", manifests: { x: "2026" }, votes: [
  { pair_id: "s:GC1", task: "GC1", family: "gc", group: "servo", set: "s", attention: false, treatment_side: "left", follow: "left", follow_pref: "treatment", stable: "", stable_pref: "", note: 'a, "b"\nc', first_voted: "t0", last_voted: "t1" }] };
const back = C.readResults(C.toCSV(doc));
assert.equal(back.reviewer, "AB"); assert.equal(back.votes[0].note, 'a, "b"\nc'); assert.equal(back.votes[0].follow_pref, "treatment");
assert.equal(C.readResults(JSON.stringify(doc)).votes.length, 1);
assert.equal(C.pref("left", "left"), "treatment"); assert.equal(C.pref("right", "left"), "control"); assert.equal(C.pref("none", "left"), "none"); assert.equal(C.pref("", "left"), "");
const ag = C.agreement([{ pair_id: "p1", follow_pref: "treatment" }, { pair_id: "p2", follow_pref: "none" }], [{ pair_id: "p1", follow_pref: "treatment" }, { pair_id: "p2", follow_pref: "control" }], "follow_pref");
assert.equal(ag.n, 2); near(ag.po, 0.5, "agreement");

if (process.argv.includes("--print")) { console.log(JSON.stringify(byGroup)); console.log(dropped); }
console.log("review.check: ok (" + pairs.length + " pairs: " + Object.entries(byGroup).map(([g, f]) => g + " " + JSON.stringify(f)).join("; ") + "; " + dropped.length + " sets dropped)");
