// Compare player: one task, the Control and Treatment arms of one test side by side on one shared clock.
// Reads the same scenes index and manifests as the Scenes section (results/media on main, or ?media=DIR/),
// and the CSV rows app.js has loaded (window.PWA_SITE, announced by the "pwa:data" event).
// Run names and groups come from runinfo.js. Deep link: ?compare=TASK&b=CONTROL&c=TREATMENT#compare-clips.
// Older three-slot links (&a=) still open: the last two filled of a, b, c become Control and Treatment.
import * as RunInfo from "./runinfo.js";
import { $, el, clear, judgeComment, passesText } from "./ui.js";
(function () {
  var QKEYS = ["a", "b", "c"];
  var MAX_RUNS = 80; // manifests fetched, newest first
  var DRIFT = 0.15; // seconds a clip may drift from the shared clock before it is re-seeked
  var END = 0.05; // a clip within this of its end counts as ended
  var api = null, started = false;
  var runs = [], mans = {}, clips = {}; // clips[task] = [{exp, t, man}] newest run first, only entries with a playable video
  var RI = RunInfo.build([], [], {});
  // mode "group": one arm group, control picked from it; mode "other": any two runs
  var sel = { mode: "group", group: "", ctl: "", trt: "", task: "" }, ctlOpen = false;
  var wanted = ["", "", ""], wantTask = "", linked = false, scrolled = false;
  var loaded = false, wantPlay = false; // loaded: manifests are in; wantPlay: start playing once the requested clips have metadata
  var S = { t: 0, playing: false, rate: 1, loop: true, fps: 16, fpsKnown: false, raf: 0, last: 0 };
  var live = []; // [{exp, v, d, endEl, lenEl}] for the rendered slots

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
  /* ---------- selection ---------- */
  function has(tk, exp) { return !!exp && (clips[tk] || []).some(function (c) { return c.exp === exp; }); }
  function clipOf(tk, exp) { return (clips[tk] || []).filter(function (c) { return c.exp === exp; })[0] || null; }
  function tasksOf(exp) { return Object.keys(clips).filter(function (tk) { return has(tk, exp); }).sort(); }
  function shared(a, b) { return tasksOf(a).filter(function (tk) { return !b || has(tk, b); }); }
  function clipExps() { return runs.map(function (r) { return r.exp; }).filter(function (e) { return tasksOf(e).length; }); }
  // arm groups with a control and at least one treatment sharing a task
  function armsOf(name) {
    var g = RI.groups[name]; if (!g) return [];
    return g.arms.map(function (a) { return a.exp; }).filter(function (e) { return tasksOf(e).length; });
  }
  function controlsOf(name) {
    var arms = armsOf(name), g = RI.groups[name];
    var c = g ? g.controls.filter(function (e) { return arms.indexOf(e) >= 0; }) : [];
    return c.length ? c : arms.slice(0, 1);
  }
  function treatmentsOf(name, ctl) { return armsOf(name).filter(function (e) { return e !== ctl && shared(ctl, e).length; }); }
  function testable(name) { var c = controlsOf(name)[0]; return !!c && treatmentsOf(name, c).length > 0; }
  function testNames() { return Object.keys(RI.groups).filter(testable); }
  function fixTask(want) {
    var ts = sel.ctl ? shared(sel.ctl, sel.trt) : [];
    var w = want || sel.task;
    sel.task = ts.indexOf(w) >= 0 ? w : ts[0] || "";
  }
  function setGroup(name, ctl, trt) {
    sel.mode = "group"; sel.group = name;
    var cs = controlsOf(name);
    sel.ctl = ctl && armsOf(name).indexOf(ctl) >= 0 ? ctl : cs[0] || "";
    var ts = treatmentsOf(name, sel.ctl);
    sel.trt = trt && ts.indexOf(trt) >= 0 ? trt : ts[0] || "";
    fixTask();
  }
  function setOther(ctl, trt) {
    sel.mode = "other"; sel.group = "";
    var es = clipExps();
    sel.ctl = ctl && es.indexOf(ctl) >= 0 ? ctl : es[0] || "";
    var ok = es.filter(function (e) { return e !== sel.ctl && shared(sel.ctl, e).length; });
    sel.trt = trt === "" ? "" : trt && es.indexOf(trt) >= 0 ? trt : ok[0] || "";
    fixTask();
  }
  // test picker order: official scored groups first, then unscored, capped, tests; newest first within each
  function testSections() {
    var names = testNames(), exps = [];
    names.forEach(function (n) { exps = exps.concat(armsOf(n)); });
    return RI.sections(exps).map(function (s) { return { title: s.title, blocks: s.blocks.filter(function (b) { return b.group; }) }; })
      .filter(function (s) { return s.blocks.length; });
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
    q.set("compare", sel.task); q.delete("a");
    if (sel.ctl) q.set("b", sel.ctl); else q.delete("b");
    if (sel.trt) q.set("c", sel.trt); else q.delete("c");
    return q;
  }
  function syncUrl() {
    if (!linked || !sel.task) return;
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
      RI = RunInfo.build(api.rows, runs, mans);
      loaded = true; choose();
    }, function () { runs = []; loaded = true; choose(); });
  }
  function choose() {
    var notes = [];
    var pair = wanted.every(Boolean) ? [wanted[1], wanted[2]] : wanted.filter(Boolean);
    if (wanted.every(Boolean)) notes.push("Showing 2 of 3 linked runs.");
    pair.forEach(function (e) { if (!tasksOf(e).length) notes.push("No published clips from " + e + " yet. They appear here once that run publishes its scenes."); });
    pair = pair.filter(function (e) { return tasksOf(e).length; });
    var ga = pair[0] && RI.get(pair[0]), gb = pair[1] && RI.get(pair[1]);
    if (linked && pair.length) {
      if (ga && ga.group && testable(ga.group) && !gb && !ga.isControl) setGroup(ga.group, null, pair[0]);
      else if (ga && ga.group && testable(ga.group) && (!gb || gb.group === ga.group)) setGroup(ga.group, pair[0], pair[1]);
      else setOther(pair[0], pair[1] || "");
      fixTask(wantTask);
      if (wantTask && sel.task !== wantTask) notes.push("No clip of " + wantTask + " from both runs. Showing " + (sel.task || "no task") + ".");
    } else {
      var first = testSections()[0];
      if (first) setGroup(first.blocks[0].group); else setOther();
      if (linked && wantTask) { fixTask(wantTask); if (sel.task !== wantTask) notes.push("No published clip of " + wantTask + " yet. Showing another task."); }
    }
    render(notes);
    syncUrl();
  }

  /* ---------- render ---------- */
  function fillRuns(sx, exps, current, none) {
    clear(sx);
    if (none) sx.appendChild(el("option", { value: "", text: "none" }));
    RI.options(exps, current, true).forEach(function (g) {
      var parent = sx;
      if (g.label) { parent = el("optgroup", { label: g.label }); sx.appendChild(parent); }
      g.options.forEach(function (o) { parent.appendChild(el("option", { value: o.value, text: o.text })); });
    });
    sx.value = current;
  }
  function render(notes) {
    pause(true);
    var pick = $("cv-pick"), empty = $("cv-empty"), bar = $("cv-bar"), grid = $("cv-grid"), nb = $("cv-notes");
    clear(grid); clear(nb); live = []; S.t = 0;
    nb.hidden = !(notes && notes.length);
    (notes || []).forEach(function (n) { nb.appendChild(el("span", { class: "badge warn", text: n })); });
    if (clipExps().length < 2) {
      pick.hidden = true; $("cv-help").hidden = true; bar.hidden = true; $("cv-ctl").hidden = true; $("cv-diff").hidden = true; empty.hidden = false;
      empty.textContent = runs.length ? "Fewer than two runs have published clips, so there is nothing to compare yet."
        : "No published clips yet. Each run that generates videos adds them to a GitHub Release.";
      return;
    }
    empty.hidden = true; pick.hidden = false; $("cv-help").hidden = false;
    var other = sel.mode === "other";
    // 1. test
    var tsel = $("cv-test"); clear(tsel);
    testSections().forEach(function (s) {
      var og = el("optgroup", { label: s.title });
      s.blocks.forEach(function (b) { var g = RI.groups[b.group]; og.appendChild(el("option", { value: "g:" + b.group, text: g.title + " · " + g.common[0] + " · " + g.state })); });
      tsel.appendChild(og);
    });
    tsel.appendChild(el("option", { value: "other", text: "Other runs: pick any two" }));
    tsel.value = other ? "other" : "g:" + sel.group;
    // 2. treatment (group) or two run pickers (other)
    $("cv-trt-wrap").hidden = other; $("cv-o1-wrap").hidden = !other; $("cv-o2-wrap").hidden = !other;
    if (!other) {
      var tr = $("cv-trt"); clear(tr);
      treatmentsOf(sel.group, sel.ctl).forEach(function (e) { var i = RI.get(e); tr.appendChild(el("option", { value: e, text: i ? i.armLabel : e })); });
      tr.value = sel.trt;
    } else {
      fillRuns($("cv-o1"), clipExps(), sel.ctl, false);
      fillRuns($("cv-o2"), clipExps().filter(function (e) { return e !== sel.ctl; }), sel.trt, true);
    }
    // 3. task
    var ks = $("cv-task"); clear(ks);
    shared(sel.ctl, sel.trt).forEach(function (k) {
      var c = clipOf(k, sel.ctl);
      ks.appendChild(el("option", { value: k, text: k + ", " + api.famName(c && c.t.family) }));
    });
    ks.value = sel.task;
    // control line: plain text; a picker only when the group has more than one plausible control
    var cl = $("cv-ctl"); clear(cl);
    var cs = other ? [] : controlsOf(sel.group);
    cl.hidden = other || !sel.ctl || !(cs.length > 1 || cs.indexOf(sel.ctl) < 0);
    if (!cl.hidden) {
      var ci = RI.get(sel.ctl);
      cl.appendChild(document.createTextNode("Control: "));
      cl.appendChild(el("b", { text: ci ? ci.armLabel : sel.ctl }));
      cl.appendChild(el("code", { class: "rawid", text: sel.ctl }));
      {
        if (!ctlOpen) {
          var cb = el("button", { type: "button", class: "linkbtn", text: "change control" });
          cb.addEventListener("click", function () { ctlOpen = true; render([]); $("cv-ctlsel").focus(); });
          cl.appendChild(cb);
        } else {
          var cx = el("select", { id: "cv-ctlsel", "aria-label": "Control run" });
          armsOf(sel.group).forEach(function (e) { var i = RI.get(e); cx.appendChild(el("option", { value: e, text: (i ? i.armLabel : e) + "  (" + e + ")" })); });
          cx.value = sel.ctl;
          cx.addEventListener("change", function (e) { linked = true; setGroup(sel.group, e.target.value, sel.trt); render([]); syncUrl(); });
          cl.appendChild(cx);
        }
      }
    }
    // the two cards
    var chosen = [[sel.ctl, "Control"], [sel.trt, "Treatment"]].filter(function (x) { return x[0] && sel.task && has(sel.task, x[0]); });
    grid.style.setProperty("--cvn", "2");
    chosen.forEach(function (x) { grid.appendChild(slotCard(clipOf(sel.task, x[0]), x[1])); });
    var df = $("cv-diff");
    clear(df);
    if (chosen.length === 2) {
      df.appendChild(document.createTextNode(RunInfo.difference(RI.get(sel.ctl), RI.get(sel.trt))));
      var g = other ? null : RI.groups[sel.group];
      if (g) df.appendChild(el("span", { class: "cvboth", text: "Both arms: " + g.common.join(", ") + (g.setupWords.length ? ", with " + g.setupWords.join(", ") : "") }));
    }
    df.hidden = chosen.length !== 2;
    bar.hidden = !live.length;
    $("cv-note").hidden = !live.length;
    if (chosen.length < 2) { nb.hidden = false; nb.appendChild(el("span", { class: "badge", text: sel.task ? "Pick a treatment to compare." : "These two runs share no task with a published clip." })); }
    updateBar();
    if (linked && !scrolled) { scrolled = true; var sec = $("compare-clips"); if (sec && sec.scrollIntoView) setTimeout(function () { sec.scrollIntoView(); }, 0); }
  }
  function dt(k, v) { return v ? [el("dt", { text: k }), el("dd", { text: v })] : []; }
  // card header: the treatment's change, and the control as "without" that change
  function headText(info, role, exp) {
    if (!info) return exp;
    if (sel.mode !== "group") return info.short;
    var c = RI.get(sel.ctl), t = RI.get(sel.trt);
    var d = c && t && c.keys && t.keys ? RunInfo.diffLabel(c.keys, t.keys) : "";
    if (role === "Treatment") return d || info.armLabel;
    return /^\+ [^;]+$/.test(d) ? "without " + d.slice(2) : info.armLabel;
  }
  function flagsLine(i) { return !i.keys ? "flags not recorded" : i.words.length ? i.words.join(", ") : "no flags"; }
  function slotCard(c, role) {
    var m = c.man, t = c.t, row = csvRow(c.exp), cap = capOf(m, row);
    var v = el("video", { muted: "", playsinline: "", preload: "auto", src: t.video, poster: t.poster || null, "aria-label": role + ": " + c.exp + ", " + t.task_id });
    v.muted = true; v.loop = false;
    var endEl = el("div", { class: "cvend", hidden: "" });
    var media = el("div", { class: "media" }, [v, endEl]);
    var s = { exp: c.exp, v: v, d: NaN, endEl: endEl, lenEl: null, failed: false };
    live.push(s);
    v.addEventListener("loadedmetadata", function () {
      if (isFinite(v.duration)) { s.d = v.duration; updateLens(); updateBar(); }
      if (wantPlay && live.every(function (x) { return x.failed || isFinite(x.d); })) { wantPlay = false; play(); }
    });
    // a failed clip leaves the shared clock: it never holds playback for buffering and never sets the length
    v.addEventListener("error", function () { s.failed = true; endEl.hidden = false; endEl.textContent = "Clip failed to load"; updateLens(); updateBar(); });
    if (!S.fpsKnown) probeFps(v);

    // score and which judge produced it
    var sj = screeningJudge(m), score, judge;
    if (runScored(m) && typeof t.mean === "number") {
      score = api.fmt(t.mean) + " / 5";
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
    var info = RI.get(c.exp);
    var dl = el("dl", { class: "cvmeta" }, [].concat(
      dt("Runner", runner + (model && model.name && model.name !== runner ? " (" + model.name + ")" : "")),
      dt("Player", playerOf(m) || (src === "dataset" ? "none, replayed moves" : "")),
      dt("Flags", flagsOf(m)),
      dt("Notes", (m && m.notes) || (row && row.notes) || ""),
      [el("dt", { text: "Clip" }), lenEl]
    ));
    var kids = [
      el("div", { class: "cvhead" }, [el("span", { class: "cvlab", text: role.toUpperCase() }), el("b", { text: headText(info, role, c.exp) }),
        el("code", { class: "rawid", text: c.exp })]),
      media,
      el("div", { class: "cvscore" }, [el("span", { class: "sc", text: score }), el("span", { class: "judge", text: judge })]),
      b,
      sel.mode !== "group" ? el("p", { class: "cvdesc", text: info ? info.label : "" }) : null,
      el("details", { class: "cvmore" }, [el("summary", { text: "Run details" }), dl])
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
    return el("article", { class: "cvslot", "data-slot": role.toLowerCase() }, kids);
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
    function pick(fn) { return function (e) { linked = true; fn(e.target.value); render([]); syncUrl(); }; }
    $("cv-test").addEventListener("change", pick(function (v) {
      ctlOpen = false;
      if (v === "other") setOther(sel.ctl, sel.trt); else setGroup(v.slice(2));
    }));
    $("cv-trt").addEventListener("change", pick(function (v) { sel.trt = v; fixTask(); }));
    $("cv-o1").addEventListener("change", pick(function (v) { setOther(v, sel.trt === v ? null : sel.trt); }));
    $("cv-o2").addEventListener("change", pick(function (v) { sel.trt = v; fixTask(); }));
    $("cv-task").addEventListener("change", pick(function (v) { sel.task = v; }));
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
    // story cards and the tour (app.js) ask for one task from two runs: detail { task, b: control, c: treatment, play }
    document.addEventListener("pwa:compare", function (e) {
      var d = e.detail || {};
      wantTask = d.task || ""; wanted = ["", d.b || "", d.c || ""]; linked = true; scrolled = true; wantPlay = !!d.play;
      if (loaded) choose();
    });
    // switching back to this tab: write the selection to a/b/c again so a copied link opens it
    document.addEventListener("pwa:mode", function (e) {
      if (e.detail === "compare" && sel.task) { linked = true; syncUrl(); }
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
