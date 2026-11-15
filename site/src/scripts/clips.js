// Clip helpers shared by the two clip pages: the Pairs section (pairs.js, compare.js) and the blind review page
// (review-core.js, review.js). Pure, no DOM.

// a clip URL the page can play: https, or same origin when an origin is given (local fixtures)
export function playableUrl(u, origin) {
  if (!u || typeof u !== "string") return false;
  if (/^https:\/\//.test(u)) return true;
  if (!origin) return false;
  try { return new URL(u, origin).origin === new URL(origin).origin; } catch (e) { return false; }
}
// a manifest's clips by task id; ok(url) decides which clip URLs count (default: any non-empty URL)
export function clipMap(man, ok) {
  var m = {};
  ((man && man.tasks) || []).forEach(function (t) { if (t && t.task_id && t.video && (!ok || ok(t.video))) m[t.task_id] = t; });
  return m;
}
// seconds -> "m:ss.s", the shared clock's time label
export function fmtT(s) {
  if (!isFinite(s)) return "-:--.-";
  s = Math.max(0, s);
  var m = Math.floor(s / 60), r = s - m * 60;
  return m + ":" + (r < 10 ? "0" : "") + r.toFixed(1);
}
