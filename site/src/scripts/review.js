// Blind review page: two clips of one task side by side, control and treatment on seeded random sides, votes kept in
// this browser only, arms revealed only after "Finish and reveal". Pure logic lives in review-core.js.
import { $, el, clear } from "./ui.js";
import { FAMINFO } from "./families.js";
import * as C from "./review-core.js";
import { fmtT } from "./clips.js";
(function () {
  var REPO = "benceruleanlu/playworld-advancement";
  var MEDIA_RAW = "https://raw.githubusercontent.com/" + REPO + "/main/results/media/";
  var BASE = (import.meta.env.BASE_URL || "/").replace(/\/?$/, "/");
  var KEY = "pwa-review-v1";
  var DRIFT = 0.15, END = 0.05;
  var mans = {}, pairs = [], dropped = [];
  var store = { last: {}, reviewers: {}, rounds: {} };
  var cur = { reviewer: "", rkey: "", group: "all", family: "all", list: [], pos: 0, q: 0, sides: {}, left: 0 };
  var storageOk = true;
  var blobs = [];

  /* ---------- storage: this browser only, and the page works without it ---------- */
  function load() {
    try { var t = KEY + "-probe"; localStorage.setItem(t, "1"); localStorage.removeItem(t); } catch (e) { storageOk = false; }
    try { var s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s && s.reviewers) store = s; } catch (e) {}
    store.rounds = store.rounds || {};
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) {} }
  // revealed: {selection key: {at, ids}}; unblinded: pair ids whose sides a reveal has shown, left out of later trials
  function recFor(key, name) {
    var r = store.reviewers[key];
    if (!r) r = store.reviewers[key] = { name: name, votes: {}, revealed: {}, unblinded: {}, pos: {} };
    if (!r.revealed || typeof r.revealed !== "object") r.revealed = {};
    r.unblinded = r.unblinded || {};
    return r;
  }
  function rec() { return recFor(cur.rkey, cur.reviewer); }
  function round(key) { return store.rounds[key] || 0; }
  function selKey() { return cur.group + "|" + cur.family; }

  /* ---------- manifests ---------- */
  function mediaOverride() {
    var q = new URLSearchParams(location.search).get("media");
    if (!q) return null;
    try { var u = new URL(q.replace(/\/?$/, "/"), location.href); return u.origin === location.origin ? u.href : null; } catch (e) { return null; }
  }
  function getJson(url) { return fetch(url, { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function getMan(exp) {
    var ov = mediaOverride(), name = exp + ".json";
    var p = ov ? getJson(ov + name) : getJson(MEDIA_RAW + name).catch(function () { return getJson(BASE + "media/" + name); });
    return p.then(function (m) { if (m && m.exp === exp) mans[exp] = m; }, function () {});
  }
  function exps() { var o = []; C.SETS.forEach(function (s) { o.push(s.ctl, s.trt); }); return o; }
  function manVersions() { var o = {}; Object.keys(mans).forEach(function (k) { o[k] = mans[k].generated || ""; }); return o; }

  /* ---------- attribution (same facts as the Scenes section) ---------- */
  function attribution(box) {
    clear(box);
    var seen = {}, models = [];
    Object.keys(mans).forEach(function (k) { var m = mans[k].model; if (m && m.name && !seen[m.name]) { seen[m.name] = 1; models.push(m); } });
    function A(href, text) { return el("a", { href: href, target: "_blank", rel: "noopener", text: text }); }
    var p = el("p", { class: "scnote" });
    if (models.length) {
      p.appendChild(document.createTextNode("Clips generated with "));
      models.forEach(function (m, i) {
        if (i) p.appendChild(document.createTextNode("; "));
        if (m.url && /^https:/.test(m.url)) p.appendChild(A(m.url, m.name)); else p.appendChild(document.createTextNode(m.name));
        var who = [m.org, m.license].filter(Boolean).join(", ");
        if (who) p.appendChild(document.createTextNode(" (" + who + ")"));
      });
      p.appendChild(document.createTextNode(". Its weights and modules run unchanged; "));
      p.appendChild(A("https://github.com/" + REPO + "/blob/main/adapters/lingbot_world2/session.py", "our session wrapper"));
      p.appendChild(document.createTextNode(" re-implements its sampling loop. "));
    }
    p.appendChild(document.createTextNode("Task images come from "));
    p.appendChild(A("https://github.com/kxding/PlayWorld", "PlayWorld"));
    p.appendChild(document.createTextNode(" (Pexels and web image search, their terms). Videos: "));
    p.appendChild(A("https://creativecommons.org/licenses/by-nc-sa/4.0/", "CC BY-NC-SA 4.0"));
    p.appendChild(document.createTextNode(", non-commercial. "));
    p.appendChild(A("https://github.com/" + REPO + "/issues/new?title=Scene+removal+request", "Request removal"));
    p.appendChild(document.createTextNode("."));
    box.appendChild(p);
  }

  /* ---------- start screen ---------- */
  function famName(f) { return FAMINFO[f] ? FAMINFO[f].name : (f || "-"); }
  function inGroup(p, g) { return g === "all" || p.group === g; }
  function inFam(p, f) { return f === "all" || p.family === f; }
  function renderStart() {
    var gs = $("rv-group"), fs = $("rv-fam");
    var g0 = gs.value || cur.group, f0 = fs.value || cur.family;
    clear(gs); clear(fs);
    function cnt(g, f) { return pairs.filter(function (p) { return inGroup(p, g) && inFam(p, f); }).length; }
    gs.appendChild(el("option", { value: "all", text: "All groups (" + cnt("all", "all") + " trials)" }));
    Object.keys(C.GROUPS).forEach(function (g) { var n = cnt(g, "all"); if (n) gs.appendChild(el("option", { value: g, text: C.GROUPS[g].name + " (" + n + ")" })); });
    if (Array.prototype.some.call(gs.options, function (o) { return o.value === g0; })) gs.value = g0;
    var g = gs.value;
    fs.appendChild(el("option", { value: "all", text: "All families (" + cnt(g, "all") + ")" }));
    C.FAMS.forEach(function (f) { var n = cnt(g, f); if (n) fs.appendChild(el("option", { value: f, text: famName(f) + " (" + n + ")" })); });
    if (Array.prototype.some.call(fs.options, function (o) { return o.value === f0; })) fs.value = f0;
    var desc = $("rv-gdesc"); clear(desc);
    (g === "all" ? Object.keys(C.GROUPS) : [g]).forEach(function (k) {
      if (!cnt(k, "all")) return;
      desc.appendChild(el("li", null, [el("b", { text: C.GROUPS[k].name + ". " }), document.createTextNode(C.GROUPS[k].what)]));
    });
    var dn = $("rv-dropped"); clear(dn); dn.hidden = !dropped.length;
    dropped.forEach(function (d) { dn.appendChild(el("li", { text: "Left out: " + C.GROUPS[d.group].name + ", " + d.why + "." })); });
    var name = $("rv-name").value.trim(), n = cnt(g, fs.value);
    $("rv-go").disabled = !name || !n;
    var r = name ? store.reviewers[name.toLowerCase()] : null, st = $("rv-state");
    var rv = r && r.revealed && typeof r.revealed === "object" ? r.revealed[g + "|" + fs.value] : null;
    var sel = pairs.filter(function (p) { return inGroup(p, g) && inFam(p, fs.value); });
    var gone = r && r.unblinded ? sel.filter(function (p) { return r.unblinded[p.id]; }).length : 0;
    st.textContent = !pairs.length ? "No clips found: the scenes manifests did not load." :
      rv ? "This selection was revealed for this name on " + rv.at.slice(0, 16).replace("T", " ") + " UTC; its votes are locked. Start shows the results." :
      gone === sel.length && gone ? "Every trial in this selection was revealed under this name. To vote again, reveal it and use \"Clear my votes and start over\" (new sides), or use another name." :
      (gone ? gone + " of " + sel.length + " trials here were revealed in another selection and are left out. " : "") +
      (r && Object.keys(r.votes).length ? Object.keys(r.votes).length + " votes saved in this browser for this name." : "");
    if (gone === sel.length && gone && !rv) $("rv-go").disabled = true;
    attribution($("rv-attr-start"));
  }
  function start() {
    cur.reviewer = $("rv-name").value.trim(); cur.rkey = cur.reviewer.toLowerCase();
    cur.group = $("rv-group").value; cur.family = $("rv-fam").value;
    if (!cur.reviewer) return;
    store.last = { reviewer: cur.reviewer, group: cur.group, family: cur.family }; save();
    var r = rec(); r.name = cur.reviewer;
    cur.sides = C.assignSides(C.sideSeed(cur.rkey, round(cur.rkey)), pairs);
    var mine = pairs.filter(function (p) { return inGroup(p, cur.group) && inFam(p, cur.family); });
    var rv = r.revealed[selKey()];
    if (rv) {
      var at = {}; (rv.ids || []).forEach(function (id, i) { at[id] = i; });
      cur.list = mine.filter(function (p) { return p.id in at; }).sort(function (a, b) { return at[a.id] - at[b.id]; });
      showReveal(); return;
    }
    var open = mine.filter(function (p) { return !r.unblinded[p.id]; });
    cur.left = mine.length - open.length;
    if (!open.length) return;
    cur.list = C.shuffled(open, C.sideSeed(cur.rkey, round(cur.rkey)) + "|" + cur.group + "|" + cur.family);
    var pk = selKey();
    cur.pos = Math.min(Math.max(0, (r.pos && r.pos[pk]) || 0), cur.list.length - 1);
    show("trial"); renderTrial();
  }
  function show(which) {
    ["start", "trial", "reveal"].forEach(function (k) { $("rv-" + k).hidden = k !== which; });
    if (which !== "trial") stopClips();
    window.scrollTo(0, 0);
  }

  /* ---------- clips: blob URLs where the host allows it, so no run name sits in the DOM ---------- */
  function stopClips() {
    S.playing = false; cancelAnimationFrame(S.raf);
    live.forEach(function (s) { try { s.v.pause(); s.v.removeAttribute("src"); s.v.load(); } catch (e) {} });
    live = [];
    blobs.forEach(function (u) { URL.revokeObjectURL(u); }); blobs = [];
  }
  // Only same-origin clips can be fetched: GitHub release downloads send no CORS header, so the fetch would always fail
  // (and log the release URL, run name included, in the console). Those play from the release URL directly.
  function sameOrigin(url) { try { return new URL(url, location.href).origin === location.origin; } catch (e) { return false; } }
  function loadClip(v, url, slot, token) {
    function direct() { if (token === S.token) { v.src = url; slot.direct = true; } }
    if (!sameOrigin(url)) { direct(); return; }
    fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.blob(); })
      .then(function (b) { if (token !== S.token) return; var u = URL.createObjectURL(b); blobs.push(u); v.src = u; })
      .catch(direct);
  }
  var S = { t: 0, playing: false, rate: 1, loop: true, raf: 0, last: 0, token: 0, waiting: false };
  var live = [];
  function dur() { var d = 0; live.forEach(function (s) { if (isFinite(s.v.duration)) d = Math.max(d, s.v.duration); }); return d; }
  // A clip is ready when it can play on from the shared time, has ended, or failed. Until both are, the clock holds and
  // both clips pause, so a slow download never leaves one clip playing beside a frozen one.
  function ready(s) {
    if (s.failed) return true;
    var v = s.v, d = v.duration; if (!isFinite(d)) return false;
    if (S.t >= d - END) return true;
    return v.readyState >= 3 && !v.seeking;
  }
  function syncTo(t, force) {
    var hold = !live.every(ready);
    live.forEach(function (s) {
      var v = s.v, d = v.duration; if (!isFinite(d)) return;
      var want = Math.min(t, Math.max(0, d - END));
      if (force || (!v.seeking && Math.abs(v.currentTime - want) > DRIFT)) { try { v.currentTime = want; } catch (e) {} }
      var shouldPlay = S.playing && !hold && t < d - END;
      if (shouldPlay && v.paused) { var pr = v.play(); if (pr && pr.catch) pr.catch(function () {}); }
      if (!shouldPlay && !v.paused) v.pause();
      v.playbackRate = S.rate;
    });
  }
  function tick(now) {
    if (!S.playing) return;
    var dt = S.last ? (now - S.last) / 1000 : 0; S.last = now;
    var D = dur();
    S.waiting = !live.every(ready);
    if (!S.waiting) S.t += dt * S.rate;
    if (D && S.t >= D) { if (S.loop) { S.t = 0; syncTo(0, true); } else { S.t = D; S.playing = false; } }
    syncTo(S.t, false); bar();
    if (S.playing) S.raf = requestAnimationFrame(tick);
  }
  function play(on) {
    S.playing = on; S.last = 0; cancelAnimationFrame(S.raf);
    if (on) { if (dur() && S.t >= dur() - END) S.t = 0; S.raf = requestAnimationFrame(tick); }
    syncTo(S.t, true); bar();
  }
  function bar() {
    var D = dur();
    $("rv-play").textContent = S.playing ? "Pause" : "Play";
    $("rv-play").setAttribute("aria-label", S.playing ? "Pause both clips" : "Play both clips");
    $("rv-seek").value = D ? String(Math.min(1, S.t / D)) : "0";
    $("rv-time").textContent = fmtT(S.t) + " / " + fmtT(D) + (S.playing && S.waiting ? " · loading" : "");
    // a clip shorter than the other holds its last frame; say so, as the compare player does
    live.forEach(function (s) {
      if (s.failed) return;
      var d = s.v.duration, ended = isFinite(d) && D - d > END && S.t >= d - END;
      s.endEl.hidden = !ended;
      if (ended) s.endEl.textContent = "Clip ended at " + fmtT(d);
    });
  }
  function wirePlayer() {
    $("rv-play").addEventListener("click", function () { play(!S.playing); });
    $("rv-restart").addEventListener("click", function () { S.t = 0; syncTo(0, true); play(true); });
    $("rv-seek").addEventListener("input", function () { var D = dur(); S.t = D * +this.value; syncTo(S.t, true); bar(); });
    $("rv-loop").addEventListener("change", function () { S.loop = this.checked; });
    Array.prototype.forEach.call(document.querySelectorAll("#rv-speed [data-rate]"), function (b) {
      b.addEventListener("click", function () {
        S.rate = +b.getAttribute("data-rate");
        Array.prototype.forEach.call(document.querySelectorAll("#rv-speed [data-rate]"), function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        syncTo(S.t, false);
      });
    });
  }

  /* ---------- trial ---------- */
  var QS = [["follow", "Which clip follows the task better?", true], ["stable", "Which looks more stable and consistent?", false]];
  var CHOICES = [["left", "Left", "1"], ["right", "Right", "2"], ["none", "No difference", "3"]];
  function vote(p) { return rec().votes[p.id] || null; }
  // the side recorded with the first vote wins, so a later change to the pair list never flips a stored vote
  function sideOf(p) { var v = vote(p); return (v && v.side) || cur.sides[p.id]; }
  function setVote(p, key, val) {
    var r = rec(), v = r.votes[p.id], now = new Date().toISOString();
    if (!v) v = r.votes[p.id] = { first: now, side: sideOf(p) };
    if (key === "note") v.note = val; else v[key] = v[key] === val ? "" : val;
    v.last = now; save();
  }
  function answered() { return cur.list.filter(function (p) { var v = vote(p); return v && v.follow; }).length; }
  function renderTrial() {
    stopClips();
    var p = cur.list[cur.pos]; if (!p) return;
    var r = rec(); r.pos = r.pos || {}; r.pos[cur.group + "|" + cur.family] = cur.pos; save();
    S.token++; S.t = 0; S.playing = false;
    var token = S.token, side = sideOf(p);
    var left = side === "left" ? p.trt : p.ctl, right = side === "left" ? p.ctl : p.trt;
    var n = answered(), total = cur.list.length;
    $("rv-progress").textContent = "Trial " + (cur.pos + 1) + " of " + total + " · " + n + " answered";
    $("rv-pbar").style.width = (total ? 100 * n / total : 0) + "%";
    // task text: the site publishes no per-task goal, so the family's question stands in
    var info = FAMINFO[p.family] || {};
    $("rv-task").textContent = p.task + " · " + famName(p.family);
    $("rv-ask").textContent = info.ask || "";
    $("rv-mode").textContent = C.GROUPS[p.group].what + (cur.left ? " " + cur.left + " trials of this selection were revealed earlier and are left out." : "");
    var grid = $("rv-grid"); clear(grid);
    [["Left", "top", left], ["Right", "bottom", right]].forEach(function (x) {
      var v = el("video", { muted: "", playsinline: "", preload: "auto", disablepictureinpicture: "", controlslist: "nodownload noremoteplayback", "aria-label": x[0] + " clip" });
      v.muted = true; v.loop = false; v.defaultMuted = true;
      v.addEventListener("contextmenu", function (e) { e.preventDefault(); });
      var media = el("div", { class: "media" }, [v]);
      var endEl = el("span", { class: "cvend", hidden: "" });
      media.appendChild(endEl);
      var slot = { v: v, endEl: endEl, direct: false, failed: false };
      v.addEventListener("loadedmetadata", function () { syncTo(S.t, true); bar(); });
      v.addEventListener("error", function () { if (v.getAttribute("src")) { slot.failed = true; endEl.hidden = false; endEl.textContent = "Clip failed to load"; } });
      live.push(slot);
      grid.appendChild(el("div", { class: "cvslot" }, [el("div", { class: "cvhead" }, [el("span", { class: "cvlab", text: x[0] }), el("span", { class: "rvpos", text: "(" + x[1] + ")" })]), media]));
      loadClip(v, x[2].video, slot, token);
    });
    bar();
    var vv = vote(p); cur.q = vv && vv.follow ? 1 : 0;
    renderQuestions(p);
    $("rv-back").disabled = cur.pos === 0;
    var all = n === total;
    $("rv-next").textContent = cur.pos === total - 1 ? (all ? "Finish and reveal" : "Next unanswered") : "Next";
    $("rv-next").classList.toggle("primary", all && cur.pos === total - 1);
    $("rv-done").hidden = !all;
  }
  function renderQuestions(p) {
    var box = $("rv-qs"); clear(box);
    var v = vote(p) || {};
    QS.forEach(function (q, qi) {
      var fs = el("fieldset", { class: "rvq" + (cur.q === qi ? " active" : ""), "data-q": q[0] });
      fs.appendChild(el("legend", { text: q[1] + (q[2] ? "" : " (optional)") }));
      var row = el("div", { class: "rvchoices" });
      CHOICES.forEach(function (c) {
        var b = el("button", { type: "button", class: "cvbtn", "aria-pressed": String(v[q[0]] === c[0]) }, [el("kbd", { text: c[2] }), " " + c[1]]);
        b.addEventListener("click", function () { answer(qi, c[0]); });
        row.appendChild(b);
      });
      fs.addEventListener("click", function () { if (cur.q !== qi) { cur.q = qi; markActive(); } });
      fs.appendChild(row); box.appendChild(fs);
    });
    var ta = $("rv-note"); ta.value = v.note || "";
  }
  function markActive() { Array.prototype.forEach.call(document.querySelectorAll(".rvq"), function (f, i) { f.classList.toggle("active", i === cur.q); }); }
  function answer(qi, val) {
    var p = cur.list[cur.pos]; setVote(p, QS[qi][0], val);
    var v = vote(p);
    if (qi === 0 && v.follow) cur.q = 1;
    var keepQ = cur.q; renderQuestions(p); cur.q = keepQ; markActive();
    var n = answered(), total = cur.list.length;
    $("rv-progress").textContent = "Trial " + (cur.pos + 1) + " of " + total + " · " + n + " answered";
    $("rv-pbar").style.width = (total ? 100 * n / total : 0) + "%";
    var all = n === total;
    $("rv-done").hidden = !all;
    $("rv-next").textContent = cur.pos === total - 1 ? (all ? "Finish and reveal" : "Next unanswered") : "Next";
    $("rv-next").classList.toggle("primary", all && cur.pos === total - 1);
  }
  function go(d) {
    var total = cur.list.length;
    if (d > 0 && cur.pos === total - 1) {
      if (answered() === total) { askReveal(); return; }
      var i = cur.list.findIndex(function (p) { var v = vote(p); return !(v && v.follow); });
      if (i >= 0) { cur.pos = i; renderTrial(); }
      return;
    }
    var np = Math.max(0, Math.min(total - 1, cur.pos + d));
    if (np !== cur.pos) { cur.pos = np; renderTrial(); }
  }
  function wireTrial() {
    $("rv-back").addEventListener("click", function () { go(-1); });
    $("rv-skip").addEventListener("click", function () { go(1); });
    $("rv-next").addEventListener("click", function () { go(1); });
    $("rv-finish").addEventListener("click", function () { askReveal(); });
    $("rv-finish2").addEventListener("click", function () { askReveal(); });
    $("rv-exit").addEventListener("click", function () { show("start"); renderStart(); });
    $("rv-note").addEventListener("input", function () { setVote(cur.list[cur.pos], "note", this.value.slice(0, 500)); });
    document.addEventListener("keydown", function (e) {
      if ($("rv-trial").hidden || e.altKey || e.ctrlKey || e.metaKey) return;
      var t = e.target && e.target.tagName;
      if (t === "TEXTAREA" || t === "INPUT" || t === "SELECT") return;
      if (e.key === "1" || e.key === "2" || e.key === "3") { e.preventDefault(); answer(cur.q, CHOICES[+e.key - 1][0]); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); cur.q = e.key === "ArrowUp" ? 0 : 1; markActive(); }
      // space always plays or pauses here, even with a button focused, so it never repeats Next or Skip (Enter presses buttons)
      else if (e.key === " " || e.key === "k") { e.preventDefault(); play(!S.playing); }
      else if (e.key === "r") { e.preventDefault(); S.t = 0; syncTo(0, true); play(true); }
    });
  }

  /* ---------- reveal ---------- */
  function exportDoc() {
    var r = rec(), votes = [];
    cur.list.forEach(function (p) {
      var v = r.votes[p.id]; if (!v) return;
      var side = v.side || cur.sides[p.id];
      votes.push({ pair_id: p.id, task: p.task, family: p.family, group: p.group, set: p.set, attention: p.attention,
        control: p.ctl.exp, treatment: p.trt.exp, treatment_side: side,
        follow: v.follow || "", follow_pref: C.pref(v.follow, side), stable: v.stable || "", stable_pref: C.pref(v.stable, side),
        note: v.note || "", first_voted: v.first || "", last_voted: v.last || "" });
    });
    var rv = r.revealed[selKey()];
    return { page_version: C.PAGE_VERSION, page: location.origin + location.pathname, exported: new Date().toISOString(), reviewer: r.name || cur.reviewer,
      round: round(cur.rkey), selection: { group: cur.group, family: cur.family, trials: cur.list.length }, revealed: rv ? rv.at : null, manifests: manVersions(), votes: votes };
  }
  function askReveal() {
    var n = answered(), total = cur.list.length;
    if (!confirm("Reveal which clip had the change? " + n + " of " + total + " trials answered. After the reveal these " + total +
      " trials are locked for this name, and other selections leave them out.")) return;
    reveal();
  }
  function reveal() {
    var r = rec(), k = selKey();
    if (!r.revealed[k]) {
      r.revealed[k] = { at: new Date().toISOString(), ids: cur.list.map(function (p) { return p.id; }) };
      cur.list.forEach(function (p) { r.unblinded[p.id] = 1; });
      save();
    }
    showReveal();
  }
  var other = null;
  // caveats that apply to the trials actually answered
  function caveats(voted) {
    var out = "";
    var seeds = voted.some(function (v) { return v.set === "stk-dev-s0" && voted.some(function (w) { return w.set === "stk-dev-s1" && w.task === v.task; }); });
    if (seeds) out += " The same task appears at two seeds in the stack group.";
    var sh = C.SHARED_CLIPS, shared = voted.some(function (v) { return v.set === sh.sets[0] && sh.tasks.indexOf(v.task) >= 0; }) && voted.some(function (v) { return v.set === sh.sets[1] && sh.tasks.indexOf(v.task) >= 0; });
    if (shared) out += " For " + sh.tasks.join(", ") + " the stack clip (seed 0) and the yaw servo control clip are the same file, so the two groups share stimuli.";
    return out;
  }
  function pct(p) { return p >= 0.001 ? p.toFixed(3) : p.toExponential(1); }
  // a header with a short label for phones (global.css th .long / .short)
  function hd(long, short) { return el("th", { class: "num" }, [el("span", { class: "long", text: long }), el("span", { class: "short", "aria-hidden": "true", text: short })]); }
  function tallyTable(caption, votes, keyFn, keys) {
    var t = el("table", { class: "rvtally" });
    t.appendChild(el("caption", { text: caption }));
    t.appendChild(el("thead", null, [el("tr", null, [el("th", { text: "" }), hd("Treatment", "Trt."), hd("Control", "Ctl."), hd("No difference", "None"), hd("Sign test p", "p")])]));
    var tb = el("tbody");
    keys.forEach(function (k) {
      var vs = votes.filter(function (v) { return k[0] === "all" || keyFn(v) === k[0]; });
      if (!vs.length && k[0] !== "all") return;
      [["follow_pref", "follows task"], ["stable_pref", "stable"]].forEach(function (q, qi) {
        var c = C.tally(vs, q[0]); if (!c.n && qi) return;
        tb.appendChild(el("tr", { class: qi ? "sub2" : "" }, [el("th", { scope: "row", text: (qi ? "" : k[1] + ", ") + q[1] }), el("td", { class: "num", text: String(c.treatment) }),
          el("td", { class: "num", text: String(c.control) }), el("td", { class: "num", text: String(c.none) }),
          c.treatment + c.control ? el("td", { class: "num" }, [pct(c.p), el("span", { class: "rvn", text: "n " + (c.treatment + c.control) })]) : el("td", { class: "num", text: "-" })]));
      });
    });
    t.appendChild(tb);
    return el("div", { class: "scroll" }, [t]);
  }
  function showReveal() {
    show("reveal");
    var doc = exportDoc(), box = $("rv-results"); clear(box);
    var voted = doc.votes.filter(function (v) { return v.follow_pref && !v.attention; });
    var att = doc.votes.filter(function (v) { return v.attention; });
    var attAll = cur.list.filter(function (p) { return p.attention; }).length;
    box.appendChild(el("p", { class: "rvsum", text: doc.reviewer + ": " + voted.length + " trials answered of " + cur.list.filter(function (p) { return !p.attention; }).length +
      " in this selection" + (cur.group === "all" ? "" : " (" + C.GROUPS[cur.group].name + ")") + (cur.family === "all" ? "" : ", " + famName(cur.family)) + "." }));
    Object.keys(C.GROUPS).forEach(function (g) {
      var vs = voted.filter(function (v) { return v.group === g; }); if (!vs.length) return;
      var G = C.GROUPS[g];
      box.appendChild(el("h3", { text: G.name }));
      box.appendChild(el("p", { class: "scnote", text: "Treatment: " + G.treat + ". Control: " + G.control + ". " + G.what }));
      box.appendChild(tallyTable("Votes by family, " + G.name, vs, function (v) { return v.family; }, [["all", "All"]].concat(C.FAMS.map(function (f) { return [f, famName(f)]; }))));
      var sets = C.SETS.filter(function (s) { return s.group === g && vs.some(function (v) { return v.set === s.id; }); });
      if (sets.length > 1) box.appendChild(tallyTable("Votes by comparison set, " + G.name + " (the sets have different baselines)", vs, function (v) { return v.set; }, sets.map(function (s) { return [s.id, s.label]; })));
    });
    if (!voted.length) box.appendChild(el("p", { class: "callout", text: "No answered trials yet." }));
    if (attAll) {
      var ok = att.filter(function (v) { return v.follow === "none"; }).length, ans = att.filter(function (v) { return v.follow; }).length;
      box.appendChild(el("h3", { text: "Attention checks" }));
      box.appendChild(el("p", { text: attAll + " trials showed two byte-identical clips (walking-only GC tasks where the yaw servo changed nothing). Expected answer: no difference. " +
        (ans ? ok + " of " + ans + " answered gave no difference" : "None answered") + (ans && attAll - ans ? "; " + (attAll - ans) + " unanswered" : "") + ". They are not in the counts above." }));
    }
    box.appendChild(el("p", { class: "callout", text: "A preference by eye is not a benchmark score and not a PlayWorld score. These counts are one reviewer's votes (" + doc.reviewer + "), n = " +
      voted.length + " trials" + (other ? "; a second reviewer's file is compared below, not added in" : "") + ". The sign test drops ties and treats every trial as independent." + caveats(voted) }));
    // every trial, now unblinded
    var det = el("details", { class: "rvall" }, [el("summary", { text: "Every trial, unblinded" })]);
    var t = el("table", { class: "rvtally" }), tb = el("tbody");
    t.appendChild(el("thead", null, [el("tr", null, ["Task", "Run pair", "Treatment side", "Follows task", "Stable", "Note"].map(function (h) { return el("th", { text: h }); }))]));
    doc.votes.forEach(function (v) {
      tb.appendChild(el("tr", null, [el("td", { text: v.task + (v.attention ? " (attention)" : "") }), el("td", { text: v.control + " vs " + v.treatment }), el("td", { text: v.treatment_side }),
        el("td", { text: v.follow_pref || "-" }), el("td", { text: v.stable_pref || "-" }), el("td", { text: v.note || "" })]));
    });
    t.appendChild(tb); det.appendChild(el("div", { class: "scroll" }, [t])); box.appendChild(det);
    renderAgreement(doc);
    attribution($("rv-attr-reveal"));
  }
  function renderAgreement(doc) {
    var box = $("rv-agree"); clear(box);
    if (!other) return;
    var mine = doc.votes.filter(function (v) { return !v.attention; });
    box.appendChild(el("h3", { text: "Agreement with " + (other.reviewer || "the imported file") }));
    [["follow_pref", "Follows the task"], ["stable_pref", "Stable and consistent"]].forEach(function (q) {
      var a = C.agreement(mine, other.votes.filter(function (v) { return !(v.attention === true || v.attention === "true"); }), q[0]);
      box.appendChild(el("p", { text: q[1] + ": " + (a.n ? a.rows.filter(function (r) { return r.a === r.b; }).length + " of " + a.n + " trials agree (" + Math.round(100 * a.po) + "%), Cohen's kappa " +
        (a.kappa === null ? "undefined (one category only)" : a.kappa.toFixed(2)) : "no trial answered by both") + "." }));
      if (q[0] === "follow_pref" && a.n) {
        var t = el("table", { class: "rvtally" }), tb = el("tbody");
        t.appendChild(el("thead", null, [el("tr", null, ["Task", "Group", "You", "Them", ""].map(function (h) { return el("th", { text: h }); }))]));
        a.rows.forEach(function (r) { tb.appendChild(el("tr", null, [el("td", { text: r.task }), el("td", { text: C.GROUPS[r.group] ? C.GROUPS[r.group].name : r.group }), el("td", { text: r.a }), el("td", { text: r.b }), el("td", { text: r.a === r.b ? "agree" : "differ" })])); });
        t.appendChild(tb); box.appendChild(el("details", null, [el("summary", { text: "Per trial" }), el("div", { class: "scroll" }, [t])]));
      }
    });
  }
  function download(name, text, type) {
    var u = URL.createObjectURL(new Blob([text], { type: type }));
    var a = el("a", { href: u, download: name }); document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(u); }, 1000);
  }
  function fileBase() { return "review-" + (cur.reviewer || "anon").replace(/[^A-Za-z0-9_-]+/g, "_") + "-" + new Date().toISOString().slice(0, 10); }
  function status(t) { $("rv-copied").textContent = t; setTimeout(function () { $("rv-copied").textContent = ""; }, 2500); }
  function wireReveal() {
    $("rv-copy-json").addEventListener("click", function () { copy(JSON.stringify(exportDoc(), null, 1)); });
    $("rv-copy-csv").addEventListener("click", function () { copy(C.toCSV(exportDoc())); });
    $("rv-dl-json").addEventListener("click", function () { download(fileBase() + ".json", JSON.stringify(exportDoc(), null, 1), "application/json"); });
    $("rv-dl-csv").addEventListener("click", function () { download(fileBase() + ".csv", C.toCSV(exportDoc()), "text/csv"); });
    $("rv-import").addEventListener("change", function () {
      var f = this.files && this.files[0]; if (!f) return;
      f.text().then(function (t) { other = C.readResults(t); renderAgreement(exportDoc()); status("Imported " + other.votes.length + " votes."); showReveal(); })
        .catch(function (e) { status("Could not read that file: " + e.message); });
    });
    $("rv-home").addEventListener("click", function () { show("start"); renderStart(); });
    $("rv-clear").addEventListener("click", function () {
      if (!confirm("Delete every vote saved in this browser for " + cur.reviewer + "? Starting over draws new sides for this name, because the reveal showed the old ones.")) return;
      delete store.reviewers[cur.rkey]; store.rounds[cur.rkey] = round(cur.rkey) + 1; save(); other = null; show("start"); renderStart();
    });
  }
  function copy(text) {
    var done = function () { status("Copied."); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () { fallback(); });
    else fallback();
    function fallback() { var ta = el("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); done(); } catch (e) { status("Copy failed; use Download."); } ta.remove(); }
  }

  /* ---------- boot ---------- */
  function boot() {
    load();
    var l = store.last || {};
    if (l.reviewer) $("rv-name").value = l.reviewer;
    $("rv-nostore").hidden = storageOk;
    cur.group = l.group || "all"; cur.family = l.family || "all";
    ["rv-name", "rv-group", "rv-fam"].forEach(function (id) { $(id).addEventListener(id === "rv-name" ? "input" : "change", renderStart); });
    $("rv-form").addEventListener("submit", function (e) { e.preventDefault(); start(); });
    wirePlayer(); wireTrial(); wireReveal();
    Promise.all(exps().map(getMan)).then(function () {
      var b = C.buildPairs(mans); pairs = b.pairs; dropped = b.dropped;
      $("rv-loading").hidden = true; $("rv-form").hidden = false;
      renderStart();
    });
  }
  boot();
})();
