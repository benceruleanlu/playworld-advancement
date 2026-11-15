// Browser check for the Pairs section: node src/scripts/pairs.browser.mjs [BASE_URL] [--shots DIR]
// Needs Playwright (require('playwright')) and a server that serves site/dist at /playworld-advancement/ with
// results/media copied to /playworld-advancement/media/. Not run in CI (no browser there); run it by hand.
// Checks: no horizontal scroll at 360, 600, 768, 900 and 1280 px; no clip download at 360 px before a tap;
// old deep links resolve; Prev/Next, keys and Auto next advance the pair; URL state round-trips; no console errors.
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const args = process.argv.slice(2);
const BASE = (args.find((a) => /^https?:/.test(a)) || "http://localhost:8765/playworld-advancement/").replace(/\/?$/, "/");
const shotDir = args.includes("--shots") ? args[args.indexOf("--shots") + 1] : "";
const Q = "?csv=experiments.csv&media=media/";
let failed = 0;
function ok(cond, name) { if (cond) console.log("ok   " + name); else { failed++; console.log("FAIL " + name); } }

const browser = await chromium.launch();
async function page(w, h, opts) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h || 900 }, deviceScaleFactor: 1, ...(opts || {}) });
  const p = await ctx.newPage();
  p.errors = []; p.mp4 = [];
  p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|net::ERR/.test(m.text())) p.errors.push(m.text()); });
  p.on("pageerror", (e) => p.errors.push(String(e)));
  p.on("request", (r) => { if (/releases\/download\/.*\.mp4/.test(r.url())) p.mp4.push(r.url()); });
  // clips and posters live on GitHub Releases; answer them locally so the check needs no network
  await p.route(/releases\/download\//, (r) => r.fulfill({ status: 404, body: "" }));
  await p.route(/raw\.githubusercontent\.com|api\.github\.com/, (r) => r.fulfill({ status: 404, body: "" }));
  return p;
}
async function ready(p) { await p.waitForFunction(() => document.querySelectorAll("#pair-grid .prcard").length > 0, null, { timeout: 20000 }); await p.waitForTimeout(400); }
const pos = (p) => p.textContent("#pr-pos");
const qs = (p) => new URL(p.url()).searchParams;

// 1. no horizontal page scroll
for (const w of [360, 600, 768, 900, 1280]) {
  const p = await page(w);
  await p.goto(BASE + Q); await ready(p);
  const sw = await p.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  ok(sw[0] <= sw[1], `no horizontal scroll at ${w}px (${sw[0]} <= ${sw[1]})`);
  if (w === 360) {
    ok(p.mp4.length === 0, "no clip request at 360px before a tap (" + p.mp4.length + ")");
    ok(await p.evaluate(() => document.querySelectorAll("#pair-grid video").length === 0), "no video elements in the grid");
    ok(await p.evaluate(() => [...document.querySelectorAll("#cv-grid video")].every((v) => v.preload === "none" && v.paused)), "phone player: preload none, paused");
    ok(await p.isVisible("#pr-sticky"), "phone sticky bar shows");
    if (shotDir) {
      await p.screenshot({ path: shotDir + "/top-360.png" });
      await p.evaluate(() => document.getElementById("pairs").scrollIntoView({ behavior: "instant" })); await p.waitForTimeout(300);
      await p.screenshot({ path: shotDir + "/pairs-360.png" });
      await p.evaluate(() => document.getElementById("pr-nav").scrollIntoView({ behavior: "instant" })); await p.waitForTimeout(300);
      await p.screenshot({ path: shotDir + "/pair-open-360.png", fullPage: false });
    }
    await p.click("#prs-play");
    await p.waitForTimeout(1500);
    ok(p.mp4.length > 0, "a tap on Play fetches the clips");
  }
  if (w === 1280 && shotDir) {
    await p.screenshot({ path: shotDir + "/top-1280.png" });
    await p.evaluate(() => document.getElementById("pairs").scrollIntoView({ behavior: "instant" })); await p.waitForTimeout(300);
    await p.screenshot({ path: shotDir + "/pairs-1280.png" });
    await p.evaluate(() => document.getElementById("pr-nav").scrollIntoView({ behavior: "instant" })); await p.waitForTimeout(300);
    await p.screenshot({ path: shotDir + "/pair-open-1280.png" });
  }
  ok(p.errors.length === 0, `no console errors at ${w}px` + (p.errors.length ? ": " + p.errors.join(" | ") : ""));
  await p.context().close();
}

// 2. prev / next, keys, auto next, URL round trip
{
  const p = await page(1280);
  await p.goto(BASE + Q); await ready(p);
  const a = await pos(p);
  ok(/^Pair 1 of \d+/.test(a), "starts at pair 1: " + a);
  await p.click("#pr-next"); const b = await pos(p);
  ok(/^Pair 2 of/.test(b), "Next advances: " + b);
  ok(qs(p).get("cmp") && qs(p).get("pair"), "URL has cmp and pair: " + new URL(p.url()).search);
  await p.focus("#pr-next");
  await p.keyboard.press("ArrowRight"); ok(/^Pair 3 of/.test(await pos(p)), "ArrowRight advances");
  await p.keyboard.press("j"); ok(/^Pair 2 of/.test(await pos(p)), "J goes back");
  await p.click("#pr-prev"); ok(/^Pair 1 of/.test(await pos(p)), "Prev goes back");
  // auto next: on, loop off, and an ended play moves on
  await p.check("#cv-auto");
  ok(!(await p.isChecked("#cv-loop")), "Auto next turns Loop off");
  await p.evaluate(() => document.dispatchEvent(new CustomEvent("pwa:ended")));
  await p.waitForTimeout(200);
  ok(/^Pair 2 of/.test(await pos(p)), "Auto next advances after a clip ends");
  // swap
  await p.click("#cv-swap");
  ok(await p.evaluate(() => document.getElementById("cv-grid").classList.contains("swapped")), "Swap sides swaps");
  // family filter and URL state round trip
  await p.click('#pr-fam [role="tab"]:nth-child(2)');
  const url = p.url(), fam = qs(p).get("fam"), at = await pos(p);
  ok(!!fam, "family filter writes fam=" + fam);
  const p2 = await page(1280); await p2.goto(url); await ready(p2);
  ok((await pos(p2)) === at && new URL(p2.url()).searchParams.get("fam") === fam, "URL state round-trips: " + at);
  // comparison picker
  const second = await p.evaluate(() => document.querySelectorAll("#pr-cmp option")[1].value);
  await p.selectOption("#pr-cmp", second);
  ok(qs(p).get("cmp") === second && /^Pair 1 of/.test(await pos(p)), "picker selects a comparison");
  // Esc closes the player, a card reopens it
  await p.focus("#pr-next"); await p.keyboard.press("Escape");
  ok(await p.isHidden("#compare-clips"), "Esc closes the player");
  ok(await p.evaluate(() => document.activeElement && document.activeElement.classList.contains("prcard")), "Esc focuses the card");
  await p.click("#pair-grid .prcard:nth-child(2)");
  ok(await p.isVisible("#compare-clips") && /^Pair 2 of/.test(await pos(p)), "a card opens its pair");
  ok(p.errors.length + p2.errors.length === 0, "no console errors in navigation" + (p.errors.concat(p2.errors).join(" | ")));
  await p.context().close(); await p2.context().close();
}

// 3. old deep links
await deepLinkRun();
async function deepLinkRun() {
  await deepLink2("?compare=OE039&b=stk14-fx-dev-v1-a1&c=stk14-fx-dev-v1-a2", "#compare-clips", async (p) =>
    /OE039/.test(await pos(p)) && !(await p.isVisible("#cv-pick")) && !qs(p).get("compare") && !!qs(p).get("cmp"), "?compare= derived triple opens the pair");
  await deepLink2("?compare=GC033&b=svgc14-fx-v1-a1&c=svgc14-fx-v1-a2", "#compare-clips", async (p) =>
    /GC033/.test(await pos(p)), "servo finding link opens its pair");
  await deepLink2("?compare=OE039&b=stk14-fx-dev-v1-a1&c=stk14-fx-dev-v1-a4", "#compare-clips", async (p) =>
    (await p.isVisible("#cv-pick")) && /Not a derived control\/treatment pair/.test(await p.textContent("#cv-notes")), "non-derived ?compare= opens hand-pick with the note");
  await deepLink2("?compare=OE039&a=stk14-fx-dev-v1-a1&b=stk14-fx-dev-v1-a2&c=stk14-fx-dev-v1-a4", "#compare-clips", async (p) =>
    (await p.isVisible("#cv-pick")) && (await p.locator("#cv-grid .cvslot").count()) === 2, "three-slot &a= link opens hand-pick");
  await deepLink2("?scenes=stk14-fx-dev-v1-a2&scene=OE039", "#scenes", async (p) =>
    (await p.isVisible("#scenes")) && (await p.inputValue("#sc-run")) === "stk14-fx-dev-v1-a2", "?scenes= opens Browse a run");
  await deepLink2("?tour=2", "", async (p) => (await p.isVisible("#tour")) && /^2 \//.test(await p.textContent("#tour-n")), "?tour=2 opens the tour");
  await deepLink2("?cmp=yaw-servo_on_caption-prompt%2Bturn-cal_fixed&fam=outsight&pair=OE047~mem14-fx-v1-a1", "#pairs", async (p) =>
    /OE047/.test(await pos(p)) && /Out-of-sight/.test(await pos(p)), "?cmp=&fam=&pair= opens that pair");
}
async function deepLink2(q, hash, test, name) {
  const p = await page(1280);
  await p.goto(BASE + q + "&csv=experiments.csv&media=media/" + hash);
  await ready(p); await p.waitForTimeout(800);
  let r = false; try { r = await test(p); } catch (e) { console.log("  " + e.message); }
  ok(r, name);
  ok(p.errors.length === 0, "no console errors: " + name + (p.errors.length ? " " + p.errors.join(" | ") : ""));
  await p.context().close();
}

await browser.close();
if (failed) { console.log(failed + " browser check(s) failed"); process.exit(1); }
console.log("pairs.browser: ok");
