// Browser check for the built review page: node src/scripts/review.browser.mjs [--shots DIR] (from site/, after npm run build).
// Serves dist/ at /playworld-advancement/ with stubbed manifests whose clip URLs carry the run names, then checks that the
// trial DOM shows no arm-identifying text, clips load through blob URLs, votes, reveal, export, import and no sideways scroll.
// Needs Playwright (not a site dependency) and, for playable clips, ffmpeg; without ffmpeg the clips 404 and the DOM checks still run.
import { createServer } from "node:http";
import { readFileSync, readdirSync, existsSync, mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { join, extname } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import assert from "node:assert/strict";
import { SETS, buildPairs, assignSides, sideSeed } from "./review-core.js";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const site = new URL("../../", import.meta.url).pathname;
const dist = join(site, "dist");
const media = new URL("../../../results/media/", import.meta.url).pathname;
const shotsAt = process.argv.indexOf("--shots");
const shots = shotsAt > 0 ? process.argv[shotsAt + 1] : null;
if (shots) mkdirSync(shots, { recursive: true });
assert.ok(existsSync(join(dist, "review/index.html")), "build the site first (npm run build)");

// two short distinct clips
const tmp = mkdtempSync(join(tmpdir(), "rvfix-"));
const clips = {};
// c is shorter, for the closed-loop treatment clips: its slot must say "Clip ended"
for (const [k, color, d] of [["a", "teal", 2], ["b", "orange", 2], ["c", "orange", 1]]) {
  const f = join(tmp, k + ".mp4");
  try { execFileSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "color=c=" + color + ":s=320x180:d=" + d + ":r=16", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-y", f]); clips[k] = readFileSync(f); } catch (e) { /* no ffmpeg: clips 404 */ }
}
const exps = SETS.flatMap((s) => [s.ctl, s.trt]);
const fixture = {};
for (const e of exps) {
  const p = join(media, e + ".json"); if (!existsSync(p)) continue;
  const m = JSON.parse(readFileSync(p, "utf8"));
  m.tasks.forEach((t) => { if (t.video) { t.video = "/playworld-advancement/__fixture/run-" + e + "/" + t.task_id + ".mp4"; t.poster = ""; } });
  fixture[e + ".json"] = JSON.stringify(m);
}
let slowClip = null;
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".csv": "text/csv", ".json": "application/json" };
const server = createServer((req, res) => {
  const u = new URL(req.url, "http://x"), path = decodeURIComponent(u.pathname);
  if (path.startsWith("/playworld-advancement/__fixture/")) {
    const rest = path.slice("/playworld-advancement/__fixture/".length);
    if (fixture[rest]) { res.writeHead(200, { "content-type": "application/json" }); return res.end(fixture[rest]); }
    const m = /^run-(.+?)\/.+\.mp4$/.exec(rest);
    const body = m && clips[/-a[13]$/.test(m[1]) ? "a" : /^stksv14-cl/.test(m[1]) ? "c" : "b"];
    // ?slow: hold one clip back for 2.5 s, to check that the shared clock waits for it
    const wait = slowClip && rest.endsWith(slowClip) ? 2500 : 0;
    if (body) { setTimeout(() => { res.writeHead(200, { "content-type": "video/mp4", "content-length": body.length }); res.end(body); }, wait); return; }
    res.writeHead(404); return res.end();
  }
  let f = path.replace(/^\/playworld-advancement\/?/, "");
  if (!f || f.endsWith("/")) f += "index.html";
  const full = join(dist, f);
  if (!full.startsWith(dist) || !existsSync(full)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "content-type": types[extname(full)] || "application/octet-stream" }); res.end(readFileSync(full));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const origin = "http://127.0.0.1:" + server.address().port;
const url = origin + "/playworld-advancement/review/?media=/playworld-advancement/__fixture/";

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
await ctx.route("**/*", (route) => (route.request().url().startsWith(origin) ? route.continue() : route.abort()));
const page = await ctx.newPage();
const errors = [], consoleErrors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
let dialogs = 0;
page.on("dialog", (d) => { dialogs++; d.accept(); });
async function noSideScroll(label) {
  for (const w of [360, 414, 768, 1024, 1280]) {
    await page.setViewportSize({ width: w, height: 900 });
    const sw = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(sw <= 0, label + " scrolls sideways at " + w + " px by " + sw);
  }
  await page.setViewportSize({ width: 1280, height: 900 });
}
async function shot(name) {
  if (!shots) return;
  for (const w of [360, 1280]) {
    await page.setViewportSize({ width: w, height: w === 360 ? 780 : 900 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(150);
    await page.screenshot({ path: join(shots, name + "-" + w + ".png"), fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
}

await page.goto(url);
await page.waitForSelector("#rv-form:not([hidden])");
assert.ok(await page.isDisabled("#rv-go"), "start needs a name");
await page.fill("#rv-name", "AB");
await page.selectOption("#rv-group", "all");
const optText = await page.textContent("#rv-group");
assert.match(optText, /All groups \(96 trials\)/);
assert.match(await page.textContent("#rv-attr-start"), /CC BY-NC-SA 4\.0/);
assert.match(await page.textContent("#rv-attr-start"), /LingBot-World v2/);
await noSideScroll("start");
await shot("start");
await page.click("#rv-go");
await page.waitForSelector("#rv-trial:not([hidden])");

// blinding: every trial visited, no run name, flag, file name or arm word in the trial's text or any attribute
const FORBIDDEN_TEXT = /control|treatment|stack|servo|flag|turn.?cal|caption|director|sink|window|stk14|svgc|stksv|lingbot|\.mp4|run-/i;
async function checkBlind(i) {
  if (clips.a) await page.waitForFunction(() => Array.from(document.querySelectorAll("#rv-grid video")).every((v) => (v.getAttribute("src") || "").startsWith("blob:") && v.readyState >= 1));
  const out = await page.evaluate((names) => {
    const trial = document.getElementById("rv-trial");
    const text = trial.innerText;
    const attrs = [];
    document.querySelectorAll("*").forEach((n) => { for (const a of n.attributes) attrs.push([n.tagName, a.name, a.value]); });
    const vids = Array.from(trial.querySelectorAll("video")).map((v) => ({ src: v.getAttribute("src") || "", poster: v.getAttribute("poster"), title: v.title, aria: v.getAttribute("aria-label") }));
    const leaks = attrs.filter(([t, n, v]) => names.some((e) => v.indexOf(e) >= 0));
    const titles = Array.from(trial.querySelectorAll("[title]")).map((n) => n.title);
    return { text, leaks, vids, titles, results: document.getElementById("rv-results").innerHTML };
  }, exps);
  assert.ok(!FORBIDDEN_TEXT.test(out.text), "trial " + i + " text leaks: " + (out.text.match(FORBIDDEN_TEXT) || [])[0] + "\n" + out.text);
  assert.deepEqual(out.leaks, [], "trial " + i + ": a run name sits in an attribute");
  assert.deepEqual(out.titles, [], "trial " + i + ": no tooltips in the trial");
  assert.equal(out.vids.length, 2);
  out.vids.forEach((v) => { assert.equal(v.poster, null, "no poster URL"); assert.match(v.aria, /^(Left|Right) clip$/); });
  if (clips.a) out.vids.forEach((v) => assert.match(v.src, /^blob:/, "clip loads through a blob URL"));
  assert.equal(out.results, "", "nothing revealed before finishing");
}
await checkBlind(0);
// synced play / pause / speed / restart
if (clips.a) {
  await page.click("#rv-play");
  await page.waitForTimeout(600);
  const t = await page.evaluate(() => Array.from(document.querySelectorAll("#rv-grid video")).map((v) => [v.paused, v.currentTime]));
  assert.ok(t.every((x) => !x[0]), "both clips play");
  assert.ok(Math.abs(t[0][1] - t[1][1]) < 0.2, "clips in sync: " + JSON.stringify(t));
  await page.click("#rv-speed [data-rate='2']");
  assert.equal(await page.evaluate(() => document.querySelector("#rv-grid video").playbackRate), 2);
  await page.click("#rv-play");
  assert.ok(await page.evaluate(() => Array.from(document.querySelectorAll("#rv-grid video")).every((v) => v.paused)), "both pause");
  assert.ok(await page.evaluate(() => Array.from(document.querySelectorAll("#rv-grid video")).every((v) => v.muted)), "no audio");
}
await noSideScroll("trial");
await shot("trial");
const firstTask = await page.textContent("#rv-task");
// keys: 1 answers question 1, 3 answers question 2, ArrowRight moves on
await page.keyboard.press("1");
assert.equal(await page.getAttribute(".rvq[data-q='follow'] button:nth-child(1)", "aria-pressed"), "true");
await page.keyboard.press("3");
assert.equal(await page.getAttribute(".rvq[data-q='stable'] button:nth-child(3)", "aria-pressed"), "true");
// space with Next focused plays the clips; it does not press Next again
await page.focus("#rv-next");
await page.keyboard.press(" ");
assert.equal(await page.textContent("#rv-task"), firstTask, "space did not move to another trial");
assert.equal(await page.textContent("#rv-play"), "Pause", "space played");
await page.keyboard.press(" ");
await page.keyboard.press("ArrowRight");
assert.match(await page.textContent("#rv-progress"), /Trial 2 of 96 · 1 answered/);
// a reload keeps votes, order and position
await page.reload();
await page.waitForSelector("#rv-form:not([hidden])");
assert.equal(await page.inputValue("#rv-name"), "AB");
await page.click("#rv-go");
await page.waitForSelector("#rv-trial:not([hidden])");
assert.match(await page.textContent("#rv-progress"), /Trial 2 of 96 · 1 answered/);
await page.keyboard.press("ArrowLeft");
assert.equal(await page.textContent("#rv-task"), firstTask, "same order after reload");
// answer 20 more trials with mixed keys, checking blinding on each
for (let i = 1; i <= 20; i++) {
  await page.keyboard.press("ArrowRight");
  await checkBlind(i);
  await page.keyboard.press(String((i % 3) + 1));
}
const sidesBefore = await page.evaluate(() => JSON.parse(localStorage.getItem("pwa-review-v1")).reviewers.ab.votes);
await page.click("#rv-finish");
await page.waitForSelector("#rv-reveal:not([hidden])");
assert.equal(dialogs, 1, "reveal asks first");
const rev = await page.textContent("#rv-results");
assert.match(rev, /Sign test p/);
assert.match(rev, /not a benchmark score/);
assert.match(await page.textContent("#rv-attr-reveal"), /Request removal/);
// export: JSON and CSV downloads
const [dj] = await Promise.all([page.waitForEvent("download"), page.click("#rv-dl-json")]);
const doc = JSON.parse(readFileSync(await dj.path(), "utf8"));
assert.equal(doc.reviewer, "AB"); assert.equal(doc.page_version, "review-2"); assert.equal(doc.round, 0); assert.ok(Object.keys(doc.manifests).length >= 12);
assert.ok(doc.votes.length >= 21 && doc.votes.every((v) => v.treatment_side && v.pair_id && v.group && v.family));
const [dc] = await Promise.all([page.waitForEvent("download"), page.click("#rv-dl-csv")]);
const csv = readFileSync(await dc.path(), "utf8");
assert.match(csv.split("\n")[0], /^reviewer,round,pair_id,task,family,group,set,attention,treatment_side,follow,follow_pref/);
// import a second reviewer who agrees on every other trial
const second = { reviewer: "CD", votes: doc.votes.map((v, i) => ({ pair_id: v.pair_id, follow_pref: i % 2 ? v.follow_pref : (v.follow_pref === "treatment" ? "control" : "treatment"), stable_pref: v.stable_pref })) };
const f2 = join(tmp, "cd.json"); writeFileSync(f2, JSON.stringify(second));
await page.setInputFiles("#rv-import", f2);
await page.waitForFunction(() => /Cohen's kappa/.test(document.getElementById("rv-agree").textContent));
assert.match(await page.textContent("#rv-agree"), /Agreement with CD/);
await noSideScroll("reveal");
await shot("reveal");
// revealed votes are locked: start goes straight to the results
await page.click("#rv-home");
await page.click("#rv-go");
await page.waitForSelector("#rv-reveal:not([hidden])");
// the reveal unblinded every trial, so another selection under this name cannot start
await page.click("#rv-home");
await page.selectOption("#rv-group", "stack");
assert.ok(await page.isDisabled("#rv-go"), "revealed trials cannot be voted again under another selection");
assert.match(await page.textContent("#rv-state"), /Every trial in this selection was revealed/);
// clear and start over: a new round with new sides
await page.selectOption("#rv-group", "all");
await page.click("#rv-go");
await page.waitForSelector("#rv-reveal:not([hidden])");
await page.click("#rv-clear");
await page.click("#rv-go");
await page.waitForSelector("#rv-trial:not([hidden])");
const round1 = await page.evaluate(() => JSON.parse(localStorage.getItem("pwa-review-v1")).rounds.ab);
assert.equal(round1, 1, "clear moves the name to round 1");
for (let i = 0; i < 20; i++) { await page.keyboard.press("1"); await page.keyboard.press("ArrowRight"); }
const after = await page.evaluate(() => JSON.parse(localStorage.getItem("pwa-review-v1")).reviewers.ab.votes);
{
  const fx = {}; for (const [k, v] of Object.entries(fixture)) { const m = JSON.parse(v); fx[m.exp] = m; }
  const all = buildPairs(fx).pairs, r0 = assignSides(sideSeed("ab", 0), all), r1 = assignSides(sideSeed("ab", 1), all);
  assert.ok(Object.keys(sidesBefore).every((k) => sidesBefore[k].side === r0[k]), "round 0 votes carry round 0 sides");
  assert.ok(Object.keys(after).length >= 20 && Object.keys(after).every((k) => after[k].side === r1[k]), "round 1 votes carry round 1 sides");
  assert.ok(all.filter((p) => r0[p.id] !== r1[p.id]).length > all.length * 0.3, "round 1 redraws sides");
}
// closed loop: the shorter clip says it ended; the clock waits for a slow clip
await page.click("#rv-exit");
await page.selectOption("#rv-group", "servo-cl");
await page.fill("#rv-name", "EF");
slowClip = null;
await page.click("#rv-go");
await page.waitForSelector("#rv-trial:not([hidden])");
if (clips.a) {
  await page.waitForFunction(() => Array.from(document.querySelectorAll("#rv-grid video")).every((v) => v.readyState >= 3));
  await page.click("#rv-loop");
  await page.click("#rv-play");
  await page.waitForFunction(() => Array.from(document.querySelectorAll("#rv-grid .cvend")).some((e) => !e.hidden && /Clip ended at 0:01/.test(e.textContent)), null, { timeout: 5000 });
  await page.click("#rv-loop");
  await page.click("#rv-play");
  // a clip that arrives 2.5 s late: Play pressed at once, the clock stays at 0 until it can play
  await page.keyboard.press("ArrowRight");
  const task = (await page.textContent("#rv-task")).split(" ")[0];
  slowClip = "stksv14-cl-gc-v1-a2/" + task + ".mp4";
  await page.keyboard.press("ArrowLeft"); await page.keyboard.press("ArrowRight");
  await page.click("#rv-play");
  await page.waitForTimeout(1200);
  assert.match(await page.textContent("#rv-time"), /^0:00\.0 .*loading/, "clock holds while a clip loads: " + await page.textContent("#rv-time"));
  await page.waitForFunction(() => !/^0:00\.0/.test(document.getElementById("rv-time").textContent), null, { timeout: 6000 });
  const ts = await page.evaluate(() => Array.from(document.querySelectorAll("#rv-grid video")).map((v) => v.currentTime));
  assert.ok(Math.abs(ts[0] - ts[1]) < 0.25, "both clips start together after the wait: " + ts);
  await page.click("#rv-play");
  slowClip = null;
}
// clips on another origin with no CORS header (as GitHub release downloads): played directly, never fetched, no console errors
{
  const other = createServer((req, res) => {
    const body = clips[/-a1\//.test(req.url) ? "a" : "b"];
    if (!body) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "content-type": "application/octet-stream", "content-length": body.length }); res.end(body);
  });
  await new Promise((r) => other.listen(0, "127.0.0.1", r));
  const o2 = "http://127.0.0.1:" + other.address().port;
  for (const k of Object.keys(fixture)) fixture[k] = fixture[k].replaceAll('"/playworld-advancement/__fixture/run-', '"' + o2 + "/run-");
  const fetched = [];
  await ctx.unroute("**/*");
  await ctx.route("**/*", (route) => { const u = route.request().url(); if (u.startsWith(o2)) { fetched.push(route.request().resourceType()); return route.continue(); } return u.startsWith(origin) ? route.continue() : route.abort(); });
  consoleErrors.length = 0;
  await page.goto(url);
  await page.waitForSelector("#rv-form:not([hidden])");
  await page.fill("#rv-name", "GH");
  await page.selectOption("#rv-group", "all");
  await page.click("#rv-go");
  await page.waitForSelector("#rv-trial:not([hidden])");
  const srcs = await page.evaluate(() => Array.from(document.querySelectorAll("#rv-grid video")).map((v) => v.getAttribute("src")));
  assert.ok(srcs.every((u) => u.startsWith(o2)), "cross-origin clips play from their own URL: " + srcs);
  if (clips.a) await page.waitForFunction(() => Array.from(document.querySelectorAll("#rv-grid video")).every((v) => v.readyState >= 2), null, { timeout: 5000 });
  assert.ok(!fetched.includes("fetch") && !fetched.includes("xhr"), "no fetch of cross-origin clips: " + fetched);
  assert.deepEqual(consoleErrors.filter((t) => /CORS|run-/.test(t)), [], "no CORS errors naming the run in the console");
  other.close();
}
// main page: the one link to the review page, no sideways scroll
await page.goto(origin + "/playworld-advancement/");
assert.equal(await page.getAttribute("#watch-note a[href$='review/']", "href"), "/playworld-advancement/review/");
assert.deepEqual(errors, [], "no page errors");
await browser.close();
server.close();
console.log("review.browser: ok" + (clips.a ? "" : " (no ffmpeg: clip playback not checked)") + (shots ? ", screenshots in " + shots : ""));
