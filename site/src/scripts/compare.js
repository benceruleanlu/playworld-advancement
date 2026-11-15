// Compare player: one task, up to three runs' clips side by side on one shared clock.
// Reads the same scenes index and manifests as the Scenes section (results/media on main, or ?media=DIR/),
// and the CSV rows app.js has loaded (window.PWA_SITE, announced by the "pwa:data" event).
// Deep link: ?compare=TASK&a=EXP&b=EXP&c=EXP#compare-clips (a = first slot, Reference; b = second, Control; c = third, Treatment).
"use strict";
(function () {
  var SLOTS = ["Reference", "Control", "Treatment"], QKEYS = ["a", "b", "c"];
  // the 14B starting-model run, preferred as the default baseline when it has a clip for the task
  var BASELINES = ["lb14-session-agent-dev-v1"];
  var MAX_RUNS = 80; // manifests fetched, newest first
  var DRIFT = 0.15; // seconds a clip may drift from the shared clock before it is re-seeked
  var END = 0.05; // a clip within this of its end counts as ended
  var api = null, started = false;
  var runs = [], mans = {}, clips = {}; // clips[task] = [{exp, t, man}] newest run first, only entries with a playable video
  var task = "", slots = ["", "", ""], wanted = ["", "", ""], wantTask = "", linked = false, scrolled = false;
  var S = { t: 0, playing: false, rate: 1, loop: true, fps: 16, fpsKnown: false, raf: 0, last: 0 };
  var live = []; // [{exp, v, d, endEl, lenEl}] for the rendered slots

  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "text") e.textContent = attrs[k];
      else if (k === "class") e.className = attrs[k];
      else if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return e;
  }
  // The judge's reason: the English display copy (translated after scoring) with a toggle for the judge's original,
  // which is authoritative; the original alone, marked untranslated, when no copy exists.
  function judgeComment(t, open) {
    if (!t.reason) return null;
    var attrs = open ? { open: "" } : null;
    if (t.reason_en) {
      var orig = el("p", { class: "jorig", text: t.reason });
      orig.hidden = true;
      var btn = el("button", { type: "button", class: "jtoggle", "aria-expanded": "false", text: "show original" });
      btn.addEventListener("click", function () {
        orig.hidden = !orig.hidden;
        btn.textContent = orig.hidden ? "show original" : "hide original";
        btn.setAttribute("aria-expanded", orig.hidden ? "false" : "true");
      });
      return el("details", attrs, [el("summary", { text: "Judge's comment (translated from the judge's original)" }),
        el("p", { text: t.reason_en }), btn, orig]);
    }
    return el("details", attrs, [el("summary", { text: "Judge's comment" }), el("p", { text: t.reason }),
      el("p", { class: "jnote", text: "judge's own words, untranslated" })]);
  }
  function passesText(t) {
    var ps = t.pass_scores || [];
    return ps.length ? "per pass " + ps.map(function (v) { return typeof v === "number" ? String(Math.round(v * 100) / 100) : "-"; }).join("/") : null;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function noop() {}
  function fmtT(s) {
    if (!isFinite(s)) return "-:--.-";
    s = Math.max(0, s);
    var m = Math.floor(s / 60), r = s - m * 60;
    return m + ":" + (r < 10 ? "0" : "") + r.toFixed(1);
  }
  // a clip URL is playable when it is https or same-origin (local fixtures)
  function playable(u) {
    if (!u) return false;
    try { var x = new URL(u, location.href); return x.protocol === "https:" || x.origin === location.origin; } catch (e) { return false; }
  }

  /* ---------- run facts ---------- */
  function runScored(m) { return !m || m.scored !== false; }
  function labels(m) { return (m && m.labels) || []; }
  function screeningJudge(m) {
    var hit = null;
    labels(m).forEach(function (l) { var x = /screened by ([^ ;()]+)/.exec(l); if (x && !hit) hit = x[1]; });
    return hit;
  }
  function csvRow(exp) {
    var rs = (api && api.rows || []).filter(function (r) { return r.exp === exp; });
    var scored = rs.filter(function (r) { return r.overall !== null; });
    return (scored.length ? scored : rs).slice(-1)[0] || null;
  }
  function capOf(m, row) {
    if (m && typeof m.max_chunks === "number" && m.max_chunks > 0) return m.max_chunks;
    if (row && typeof row.max_chunks === "number" && row.max_chunks > 0) return row.max_chunks;
    if (row && api.isCapped(row)) return -1; // capped, count unknown
    if (labels(m).some(function (l) { return /^capped/i.test(l); })) return -1;
    return 0;
  }
  function playerOf(m) {
    if (m && m.player_model) return m.player_model;
    var a = (m && m.runner_args) || [], out = "";
    a.forEach(function (x, i) { if (x === "--agent-model" && a[i + 1]) out = a[i + 1]; else if (/^--agent-model=/.test(x)) out = x.split("=")[1]; });
    return out;
  }
  function flagsOf(m) {
    var a = (m && m.runner_args) || [], out = [];
    for (var i = 0; i < a.length; i++) {
      if (a[i] === "--agent-model") { i++; continue; }
      if (/^--agent-model=/.test(a[i])) continue;
      out.push(a[i]);
    }
    return out.join(" ");
  }
  function official14b(m) {
    return m && m.runner === "lingbot_world2" && runScored(m) && !labels(m).length && (m.action_source === "agent" || m.action_source === "refined");
  }

  /* ---------- selection ---------- */
  function tasksWithPairs() { return Object.keys(clips).filter(function (k) { return clips[k].length >= 2; }); }
  function has(tk, exp) { return !!exp && (clips[tk] || []).some(function (c) { return c.exp === exp; }); }
  function defaultsFor(tk, keep) {
    var c = (clips[tk] || []).map(function (x) { return x.exp; });
    var out = ["", "", ""], used = {};
    (keep || []).forEach(function (e, i) { if (has(tk, e) && !used[e]) { out[i] = e; used[e] = 1; } });
    function take(e) { used[e] = 1; return e; }
    if (!out[0]) {
      var b = BASELINES.filter(function (e) { return c.indexOf(e) >= 0 && !used[e]; })[0]
        || c.filter(function (e) { return !used[e] && official14b(mans[e]); }).slice(-1)[0] || "";
      if (b) out[0] = take(b);
    }
    // newest first, but runs with an official score and no cap ahead of capped or unscored ones
    var rest = c.filter(function (e) { return !used[e]; });
    function good(e) { var r = csvRow(e); return !capOf(mans[e], r) && (runScored(mans[e]) || !!(r && r.overall != null)); }
    rest = rest.filter(good).concat(rest.filter(function (e) { return !good(e); }));
    // two arms of one A/B (shared prefix, -a1 / -a2): control in the second slot, arm in the third
    if (!out[1] && !out[2]) {
      for (var i = 0; i < rest.length; i++) {
        var mm = /^(.*-a)(\d+)$/.exec(rest[i]); if (!mm || !good(rest[i])) continue;
        var sib = rest.filter(function (e) { var k = /^(.*-a)(\d+)$/.exec(e); return k && k[1] === mm[1] && e !== rest[i] && good(e); });
        if (sib.length) {
          var pair = [rest[i]].concat(sib).sort(function (a, b) { return +/(\d+)$/.exec(a)[1] - +/(\d+)$/.exec(b)[1]; });
          out[1] = take(pair[0]); out[2] = take(pair[pair.length - 1]);
          rest = rest.filter(function (e) { return !used[e]; });
          break;
        }
      }
    }
    if (!out[2] && rest.length) out[2] = take(rest.shift());
    if (!out[1] && rest.length) out[1] = take(rest.shift());
    if (!out[0] && rest.length) out[0] = take(rest.pop());
    return out;
  }
  function defaultTask() {
    var pairs = tasksWithPairs();
    for (var i = 0; i < runs.length; i++) {
      var m = mans[runs[i].exp]; if (!m) continue;
      var hit = (m.tasks || []).filter(function (t) { return pairs.indexOf(t.task_id) >= 0; })[0];
      if (hit) return hit.task_id;
    }
    return pairs.sort()[0] || "";
  }

  /* ---------- URL ---------- */
  function readUrl() {
    var q = new URLSearchParams(location.search);
    wantTask = q.get("compare") || "";
    linked = !!wantTask;
    wanted = QKEYS.map(function (k) { return linked ? (q.get(k) || "") : ""; });
  }
  function linkFor() {
    var q = new URLSearchParams(location.search);
    q.set("compare", task);
    QKEYS.forEach(function (k, i) { if (slots[i]) q.set(k, slots[i]); else q.delete(k); });
    return q;
  }
  function syncUrl() {
    if (!linked || !task) return;
    try { history.replaceState(null, "", location.pathname + "?" + linkFor().toString() + "#compare-clips"); } catch (e) { /* sandboxed */ }
  }

  /* ---------- load ---------- */
  function start() {
    if (started || !window.PWA_SITE) return;
    started = true; api = window.PWA_SITE;
    readUrl();
    api.getJson("index.json").then(function (ix) {
      runs = ((ix && ix.runs) || []).slice().sort(function (a, b) { return a.generated < b.generated ? 1 : a.generated > b.generated ? -1 : 0; }).slice(0, MAX_RUNS);
      return Promise.all(runs.map(function (r) {
        return api.getJson(r.exp + ".json").then(function (m) { if (m && m.exp === r.exp) mans[r.exp] = m; }, noop);
      }));
    }).then(function () {
      runs.forEach(function (r) {
        var m = mans[r.exp]; if (!m) return;
        (m.tasks || []).forEach(function (t) {
          if (!playable(t.video)) return;
          (clips[t.task_id] = clips[t.task_id] || []).push({ exp: r.exp, t: t, man: m });
        });
      });
      choose();
    }, function () { runs = []; choose(); });
  }
  function choose() {
    var notes = [];
    if (linked && wantTask && !clips[wantTask]) notes.push("No published clip of " + wantTask + " yet. Showing another task.");
    else if (linked && wantTask && clips[wantTask].length < 2) notes.push("Only one run has a published clip of " + wantTask + ".");
    task = linked && clips[wantTask] ? wantTask : defaultTask();
    if (!clips[task]) task = "";
    if (task && task === wantTask && wanted.some(Boolean)) {
      // a deep link names the runs: keep its slots as given, empty where that run has no clip yet
      slots = wanted.map(function (e, i) {
        if (e && !has(task, e)) notes.push("No clip of " + task + " from " + e + " yet (" + SLOTS[i] + "). It appears here once that run publishes its scenes.");
        return has(task, e) ? e : "";
      });
    } else slots = task ? defaultsFor(task) : ["", "", ""];
    // a two-run link (a+b, a+c or b+c) opens as Control and Treatment so the pickers match the cards
    var f = slots.filter(Boolean);
    if (f.length === 2) slots = ["", f[0], f[1]];
    render(notes);
  }

  /* ---------- render ---------- */
  function render(notes) {
    pause(true);
    var pick = $("cv-pick"), empty = $("cv-empty"), bar = $("cv-bar"), grid = $("cv-grid"), nb = $("cv-notes");
    clear(grid); clear(nb); live = []; S.t = 0;
    nb.hidden = !(notes && notes.length);
    (notes || []).forEach(function (n) { nb.appendChild(el("span", { class: "badge warn", text: n })); });
    var pairs = tasksWithPairs();
    if (!pairs.length || !task) {
      pick.hidden = true; $("cv-help").hidden = true; bar.hidden = true; $("cv-note").hidden = true; empty.hidden = false;
      empty.textContent = runs.length ? "Fewer than two runs share a task with a published clip, so there is nothing to compare yet."
        : "No published clips yet. Each run that generates videos adds them to a GitHub Release.";
      return;
    }
    empty.hidden = true; pick.hidden = false; $("cv-help").hidden = false;
    var ts = $("cv-task"); clear(ts);
    var opts = pairs.slice();
    if (opts.indexOf(task) < 0) opts.push(task);
    opts.sort().forEach(function (k) {
      var fam = clips[k][0].t.family;
      ts.appendChild(el("option", { value: k, text: k + ", " + api.famName(fam) + " (" + clips[k].length + " runs)" }));
    });
    ts.value = task;
    SLOTS.forEach(function (_, i) {
      var s = $("cv-s" + i); clear(s);
      s.appendChild(el("option", { value: "", text: "none" }));
      clips[task].forEach(function (c) {
        var tags = [];
        var cr = csvRow(c.exp);
        if (!runScored(c.man) && !(cr && cr.overall !== null)) tags.push(screeningJudge(c.man) ? "screening only" : "not scored");
        if (capOf(c.man, csvRow(c.exp))) tags.push("capped");
        var o = el("option", { value: c.exp, text: c.exp + (tags.length ? " (" + tags.join(", ") + ")" : "") });
        if (slots.indexOf(c.exp) >= 0 && slots[i] !== c.exp) o.disabled = true;
        s.appendChild(o);
      });
      s.value = slots[i];
    });
    var chosen = slots.map(function (e, i) { return [e, i]; }).filter(function (x) { return x[0]; });
    grid.style.setProperty("--cvn", String(Math.max(1, chosen.length)));
    chosen.forEach(function (x) {
      var c = clips[task].filter(function (y) { return y.exp === x[0]; })[0];
      grid.appendChild(slotCard(c, x[1]));
    });
    bar.hidden = !live.length;
    $("cv-note").hidden = !live.length;
    if (chosen.length < 2) { nb.hidden = false; nb.appendChild(el("span", { class: "badge", text: "Pick a second run to compare." })); }
    updateBar();
    if (linked && !scrolled) { scrolled = true; var sec = $("compare-clips"); if (sec && sec.scrollIntoView) setTimeout(function () { sec.scrollIntoView(); }, 0); }
  }
  // card header by what is filled: two clips are always CONTROL then TREATMENT, one clip has no role
  function roleOf(i) {
    var f = slots.map(function (e, k) { return e ? k : -1; }).filter(function (k) { return k >= 0; });
    if (f.length === 1) return "";
    if (f.length === 2) return f.indexOf(i) === 0 ? "Control" : "Treatment";
    return SLOTS[i];
  }
  function dt(k, v) { return v ? [el("dt", { text: k }), el("dd", { text: v })] : []; }
  function slotCard(c, i) {
    var m = c.man, t = c.t, row = csvRow(c.exp), cap = capOf(m, row);
    var v = el("video", { muted: "", playsinline: "", preload: "auto", src: t.video, poster: t.poster || null, "aria-label": (roleOf(i) ? roleOf(i) + ": " : "") + c.exp + ", " + t.task_id });
    v.muted = true; v.loop = false;
    var endEl = el("div", { class: "cvend", hidden: "" });
    var media = el("div", { class: "media" }, [v, endEl]);
    var s = { exp: c.exp, v: v, d: NaN, endEl: endEl, lenEl: null, failed: false };
    live.push(s);
    v.addEventListener("loadedmetadata", function () { if (isFinite(v.duration)) { s.d = v.duration; updateLens(); updateBar(); } });
    // a failed clip leaves the shared clock: it never holds playback for buffering and never sets the length
    v.addEventListener("error", function () { s.failed = true; endEl.hidden = false; endEl.textContent = "Clip failed to load"; updateLens(); updateBar(); });
    if (!S.fpsKnown) probeFps(v);

    // score and which judge produced it
    var sj = screeningJudge(m), score, judge;
    if (runScored(m) && typeof t.mean === "number") {
      score = api.fmt(t.mean);
      judge = "official judge (Gemini 3.1 Pro)" + (row && row.passes ? ", mean of " + row.passes + " passes" : "") + (passesText(t) ? " (" + passesText(t) + ")" : "");
    } else if (runScored(m)) { score = "no score"; judge = "official judge, no usable score for this task"; }
    else if (row && row.overall !== null) { score = "no score"; judge = "scored by the official judge (run mean " + api.fmt(row.overall) + "), but this clip's manifest has no per-task score"; }
    else if (sj) { score = "no score"; judge = "screening judge " + sj + " only; screening scores are not shown"; }
    else { score = "no score"; judge = "no judge has scored this run"; }

    var b = el("div", { class: "badges" });
    function badge(cls, text, title) { b.appendChild(el("span", { class: "badge" + (cls ? " " + cls : ""), text: text, title: title || null })); }
    var st = t.status || [], ok = st.length === 1 && st[0] === "ok";
    if (st.length && !(st.length === 1 && st[0] === "not scored")) badge(ok ? "ok" : "warn", st.join(", "), "Verifier status for this task");
    if (cap) badge("warn", cap > 0 ? "capped smoke, " + cap + " chunks" : "capped smoke", "Each rollout stopped early. A behaviour check, never comparable to a real score.");
    if (!runScored(m) && !(row && row.overall !== null)) badge("warn", sj ? "screening judge only" : "not scored", "No official verifier score for this run.");
    var branch = (m && m.branch) || (row && row.branch) || "";
    if (branch && branch !== "main") badge("warn", "code not merged", "Run from branch " + branch + ". The code behind it is not merged into main yet.");
    var src = (m && m.action_source) || (row && row.action_source) || "";
    var scripted = (row && api.isScripted(row)) || /--lingbot-scripted-player/.test(flagsOf(m));
    if (src === "dataset") badge("warn", "open loop, A/B only", "Fixed action scripts from the dataset, no AI player. Used for A/B tests only, never for final scores.");
    else if (scripted) badge("warn", "scripted moves, test only", "The scripted player replayed the dataset moves chunk by chunk; no AI player chose them.");
    else if (src === "agent" || src === "refined") badge("ok", "AI played", "An AI player chose every move while the world was being generated.");
    if (!cap && !scripted && row && runScored(m) && api.isSmoke(row)) badge("warn", "tiny test run", "Too few tasks or a single scoring pass to estimate a score.");

    var model = m && m.model, runner = (m && m.runner) || (row && row.runner) || "";
    var lenEl = el("dd", { text: "loading" });
    s.lenEl = lenEl; s.cap = cap;
    var dl = el("dl", { class: "cvmeta" }, [].concat(
      dt("Runner", runner + (model && model.name && model.name !== runner ? " (" + model.name + ")" : "")),
      dt("Player", playerOf(m) || (src === "dataset" ? "none, replayed moves" : "")),
      dt("Flags", flagsOf(m)),
      dt("Notes", (m && m.notes) || (row && row.notes) || ""),
      [el("dt", { text: "Clip" }), lenEl]
    ));
    var kids = [
      el("div", { class: "cvhead" }, (roleOf(i) ? [el("span", { class: "cvlab", text: roleOf(i).toUpperCase() })] : []).concat([el("b", { text: c.exp })])),
      media,
      el("div", { class: "cvscore" }, [el("span", { class: "sc", text: score }), el("span", { class: "judge", text: judge })]),
      b, dl
    ];
    var jc = judgeComment(t, true); if (jc) kids.push(jc);
    if (model && model.name) {
      var cred = el("p", { class: "cvcred" }, ["Generated with "]);
      if (model.url && /^https:/.test(model.url)) cred.appendChild(el("a", { href: model.url, target: "_blank", rel: "noopener", text: model.name }));
      else cred.appendChild(document.createTextNode(model.name));
      var who = [model.org, model.license].filter(Boolean).join(", ");
      cred.appendChild(document.createTextNode((who ? " (" + who + ")" : "") + "."));
      kids.push(cred);
    }
    return el("article", { class: "cvslot", "data-slot": roleOf(i).toLowerCase() || "single" }, kids);
  }
  function maxDur() {
    var d = 0; live.forEach(function (s) { if (!s.failed && isFinite(s.d) && s.d > d) d = s.d; });
    return d;
  }
  function updateLens() {
    var D = maxDur();
    live.forEach(function (s) {
      if (!s.lenEl) return;
      if (s.failed) { s.lenEl.textContent = "failed to load"; return; }
      if (!isFinite(s.d)) { s.lenEl.textContent = "loading"; return; }
      var txt = s.d.toFixed(1) + " s";
      if (s.cap > 0) txt += ", capped at " + s.cap + " chunks";
      if (D - s.d > END) txt += "; shorter than the longest clip (" + D.toFixed(1) + " s), holds its last frame after " + fmtT(s.d);
      s.lenEl.textContent = txt;
    });
  }

  /* ---------- shared clock ---------- */
  function probeFps(v) {
    if (!v.requestVideoFrameCallback) return;
    var last = null, ds = [];
    function cb(now, md) {
      if (last !== null) { var d = md.mediaTime - last; if (d > 0.004 && d < 0.5) ds.push(d); }
      last = md.mediaTime;
      if (ds.length < 6) { v.requestVideoFrameCallback(cb); return; }
      ds.sort(function (a, b) { return a - b; });
      var f = Math.round(1 / ds[0]);
      if (f >= 5 && f <= 120) { S.fps = f; S.fpsKnown = true; updateBar(); }
    }
    v.requestVideoFrameCallback(cb);
  }
  function seekOne(s, t) {
    var x = isFinite(s.d) ? Math.min(t, Math.max(0, s.d - 0.01)) : t;
    try { if (Math.abs(s.v.currentTime - x) > 0.001) s.v.currentTime = x; } catch (e) { /* not ready */ }
  }
  function seekAll() { live.forEach(function (s) { seekOne(s, S.t); }); updateBar(); }
  function play() {
    var D = maxDur(); if (!D) return;
    if (S.t >= D - END) S.t = 0;
    seekAll();
    S.playing = true; S.last = performance.now();
    live.forEach(function (s) { s.v.playbackRate = S.rate; });
    cancelAnimationFrame(S.raf); S.raf = requestAnimationFrame(tick);
    updateBar();
  }
  function pause(quiet) {
    S.playing = false; cancelAnimationFrame(S.raf);
    live.forEach(function (s) { if (!s.v.paused) s.v.pause(); });
    if (!quiet) seekAll();
  }
  function tick(now) {
    if (!S.playing) return;
    var dts = Math.min(0.25, (now - S.last) / 1000); S.last = now;
    var D = maxDur();
    var hold = live.some(function (s) { return !s.failed && isFinite(s.d) && S.t < s.d - END && s.v.readyState < 3; });
    if (!hold) S.t += dts * S.rate;
    if (S.t >= D) {
      if (S.loop) { S.t = 0; live.forEach(function (s) { seekOne(s, 0); }); }
      else { S.t = D; pause(); updateBar(); return; }
    }
    live.forEach(function (s) {
      if (s.failed) return;
      var on = isFinite(s.d) && S.t < s.d - END;
      if (on && !hold) {
        if (s.v.paused && !s.v.ended) { s.v.playbackRate = S.rate; var p = s.v.play(); if (p && p.catch) p.catch(noop); }
        if (Math.abs(s.v.currentTime - S.t) > DRIFT * Math.max(1, S.rate)) seekOne(s, S.t);
      } else {
        if (!s.v.paused) s.v.pause();
        if (!on && isFinite(s.d)) seekOne(s, s.d);
      }
    });
    updateBar();
    S.raf = requestAnimationFrame(tick);
  }
  function step(n) {
    pause(true);
    var D = maxDur(); if (!D) return;
    var f = Math.floor(S.t * S.fps + 1e-6) + n;
    var last = Math.max(0, Math.ceil(D * S.fps) - 1);
    f = Math.max(0, Math.min(last, f));
    S.t = f / S.fps + 0.001;
    seekAll();
  }
  function updateBar() {
    var D = maxDur(), seek = $("cv-seek");
    seek.max = String(D || 1);
    if (document.activeElement !== seek || S.playing) seek.value = String(Math.min(S.t, D || 0));
    var frame = Math.floor(S.t * S.fps + 1e-6);
    $("cv-time").textContent = fmtT(S.t) + " / " + fmtT(D) + " · frame " + frame + (S.fpsKnown ? "" : " (16 fps assumed)");
    var pb = $("cv-play");
    pb.textContent = S.playing ? "Pause" : "Play"; pb.setAttribute("aria-label", S.playing ? "Pause all" : "Play all");
    pb.disabled = !D;
    live.forEach(function (s) {
      var ended = isFinite(s.d) && D - s.d > END && S.t >= s.d - END;
      if (s.failed) return;
      s.endEl.hidden = !ended;
      if (ended) s.endEl.textContent = "Clip ended at " + fmtT(s.d);
    });
  }

  /* ---------- wiring ---------- */
  function wire() {
    $("cv-task").addEventListener("change", function (e) {
      linked = true; task = e.target.value; slots = defaultsFor(task, slots); render([]); syncUrl();
    });
    SLOTS.forEach(function (_, i) {
      $("cv-s" + i).addEventListener("change", function (e) { linked = true; slots[i] = e.target.value; render([]); syncUrl(); });
    });
    $("cv-play").addEventListener("click", function () { if (S.playing) pause(); else play(); });
    $("cv-back").addEventListener("click", function () { step(-1); });
    $("cv-fwd").addEventListener("click", function () { step(1); });
    var seek = $("cv-seek"), wasPlaying = false;
    seek.addEventListener("pointerdown", function () { wasPlaying = S.playing; if (S.playing) pause(true); });
    seek.addEventListener("input", function () { if (S.playing) pause(true); S.t = Number(seek.value) || 0; seekAll(); });
    seek.addEventListener("change", function () { if (wasPlaying) { wasPlaying = false; play(); } });
    Array.prototype.forEach.call(document.querySelectorAll("#cv-bar [data-rate]"), function (b) {
      b.addEventListener("click", function () {
        S.rate = Number(b.getAttribute("data-rate")) || 1;
        Array.prototype.forEach.call(document.querySelectorAll("#cv-bar [data-rate]"), function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        live.forEach(function (s) { s.v.playbackRate = S.rate; });
      });
    });
    $("cv-loop").addEventListener("change", function (e) { S.loop = e.target.checked; });
    // switching back to this tab: write the selection to a/b/c again so a copied link opens it
    document.addEventListener("pwa:mode", function (e) {
      if (e.detail === "compare" && task) { linked = true; syncUrl(); }
    });
    $("cv-link").addEventListener("click", function () {
      var url = location.origin + location.pathname + "?" + linkFor().toString() + "#compare-clips", note = $("cv-copied");
      linked = true; syncUrl();
      function done(t) { note.textContent = t; setTimeout(function () { note.textContent = ""; }, 1800); }
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(function () { done("Copied"); }, function () { done("Link is in the address bar"); });
      else done("Link is in the address bar");
    });
    // keyboard inside the section: space plays or pauses, comma and period step one frame
    $("compare-clips").addEventListener("keydown", function (e) {
      var tg = e.target && e.target.tagName;
      if (tg === "SELECT" || tg === "INPUT" && e.target.type !== "range" || !live.length) return;
      if (e.key === "," || e.key === ".") { e.preventDefault(); step(e.key === "," ? -1 : 1); }
      else if (e.key === " " && tg !== "BUTTON" && tg !== "SUMMARY" && tg !== "A") { e.preventDefault(); if (S.playing) pause(); else play(); }
    });
  }

  if (!$("compare-clips")) return;
  wire();
  if (window.PWA_SITE) start(); else document.addEventListener("pwa:data", start);
})();
