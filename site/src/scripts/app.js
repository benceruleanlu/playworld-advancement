// Client-side results page: fetches results/experiments.csv from main at view time.
import * as RunInfo from "./runinfo.js";
import { $, el, clear, fmt, judgeComment, passesText, badge, segmented, toggleFull } from "./ui.js";
(function () {
  var REPO = "benceruleanlu/playworld-advancement";
  var RAW = "https://raw.githubusercontent.com/" + REPO + "/main/results/experiments.csv";
  var COMMIT = "https://github.com/" + REPO + "/commit/";
  var TARGET = 2.12;
  var FALLBACK_STD = Math.sqrt(0.011);
  var FULL_TASKS = 171;
  var DEV_TASKS = 24;
  var FAMS = [["gc", "GC"], ["if", "IF"], ["insight", "Insight"], ["outsight", "Out-of-sight"]];
  var REFS = [
    { exp: "Genie 3", gc: 2.74, if: 2.40, insight: 1.51, outsight: 1.81, overall: 2.12 },
    { exp: "LingBot-World2", gc: 2.04, if: 2.13, insight: 1.95, outsight: 1.16, overall: 1.82 },
    { exp: "SANA-WM", gc: 1.72, if: 1.89, insight: 1.13, outsight: 1.16, overall: 1.48 },
    { exp: "Matrix-Game-3.0", gc: 1.30, if: 1.25, insight: 1.00, outsight: 1.00, overall: 1.14 }
  ];
  REFS.forEach(function (r) { r.ref = true; });
  var GENIE = REFS[0];

  /* ---------- helpers ---------- */
  var SVGNS = "http://www.w3.org/2000/svg";
  function sv(tag, attrs, kids) {
    var e = document.createElementNS(SVGNS, tag);
    if (attrs) for (var k in attrs) {
      if (k === "text") e.textContent = attrs[k];
      else if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c) e.appendChild(c); });
    return e;
  }
  function dashCell(td) { td.appendChild(el("span", { class: "dash", text: "-" })); }
  function isTest(r) { return /fake_runner/.test(r.runner || ""); }
  /* Score-less status row the experiment workflow writes while a run is in flight, or when it failed. Not a result. */
  function isLive(r) { return r.overall === null && /^(running|generated|failed|cancelled)$/.test(r.status || ""); }
  // a status row still saying running long after the ~6 h job cap: the run ended without writing a final status
  var STALE_MS = 7 * 3600000;
  function isStale(r) { return r.status === "running" && r.overall === null && r.t !== null && Date.now() - r.t > STALE_MS; }
  // ended without a result: failed, cancelled, or a stale running row. Hidden by default.
  function isEnded(r) { return isLive(r) && (r.status === "failed" || r.status === "cancelled" || isStale(r)); }
  function isOpen(r) { return r.action_source === "dataset"; }
  // scripted player (--lingbot-scripted-player): closed-loop harness but moves replayed from the dataset, no AI player; A/B only
  function isScripted(r) { return /scripted player/i.test(r.notes || ""); }
  function isClosed(r) { return (r.action_source === "agent" || r.action_source === "refined") && !isScripted(r); }
  function isPartial(r) { return r.split !== "all" || (r.n_tasks !== null && r.n_tasks < FULL_TASKS); }
  // capped smoke tier, a behaviour check only: each rollout was cut to fewer agent chunks than the official 30 (csv max_chunks, or for rows from
  // before that column an smk-/smkNN- name or notes saying capped smoke); never comparable to a real score
  function isCapped(r) { return (typeof r.max_chunks === "number" && r.max_chunks > 0) || /^smk\d*-/.test(r.exp) || /capped smoke/i.test(r.notes || ""); }
  // real run too small to estimate a score: fewer than a dev split of tasks, or a single verifier pass
  function isSmoke(r) { return !isTest(r) && (isCapped(r) || isScripted(r) || (r.n_tasks !== null && r.n_tasks < DEV_TASKS) || (r.passes !== null && r.passes < 2)); }
  function pad2(n) { return n < 10 ? "0" + n : "" + n; }
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function fmtTime(t) {
    var d = new Date(t);
    return MON[d.getUTCMonth()] + " " + d.getUTCDate() + " " + pad2(d.getUTCHours()) + ":" + pad2(d.getUTCMinutes());
  }

  /* ---------- CSV (RFC 4180: quoted fields, commas, doubled quotes, embedded newlines) ---------- */
  function parseCSV(text) {
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
    var rows = [], row = [], f = "", q = false, i = 0, n = text.length, c;
    while (i < n) {
      c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { f += '"'; i += 2; continue; } q = false; i++; continue; }
        f += c; i++; continue;
      }
      if (c === '"') { q = true; i++; continue; }
      if (c === ",") { row.push(f); f = ""; i++; continue; }
      if (c === "\r") { i++; continue; }
      if (c === "\n") { row.push(f); rows.push(row); row = []; f = ""; i++; continue; }
      f += c; i++;
    }
    if (f !== "" || row.length) { row.push(f); rows.push(row); }
    return rows.filter(function (r) { return !(r.length === 1 && r[0].trim() === ""); });
  }
  function num(s) {
    if (s === undefined || s === null) return null;
    s = String(s).trim();
    if (s === "") return null;
    var v = Number(s);
    return isFinite(v) ? v : null;
  }
  function toRows(text) {
    var t = parseCSV(text);
    if (!t.length) throw new Error("empty csv");
    var head = t[0].map(function (h) { return h.trim(); });
    if (head.indexOf("exp") < 0) throw new Error("no exp column");
    var out = [];
    t.slice(1).forEach(function (cells, idx) {
      var o = {};
      head.forEach(function (h, j) { o[h] = (cells[j] === undefined ? "" : cells[j]); });
      if (!o.exp || !o.exp.trim()) return;
      var ts = Date.parse(o.timestamp);
      out.push({
        exp: o.exp.trim(), split: (o.split || "").trim(), t: isFinite(ts) ? ts : null, ts: o.timestamp || "",
        sha: (o.git_sha || "").trim(), runner: (o.runner || "").trim(), action_source: (o.action_source || "").trim(),
        gc: num(o.gc), if: num(o.if), insight: num(o.insight), outsight: num(o.outsight),
        overall: num(o.overall), overall_std: num(o.overall_std), passes: num(o.passes),
        n_tasks: num(o.n_tasks), n_missing: num(o.n_missing), n_dropped: num(o.n_dropped), notes: (o.notes || "").trim(), branch: (o.branch || "").trim(),
        status: (o.status || "").trim().toLowerCase(), run_url: (o.run_url || "").trim(), max_chunks: num(o.max_chunks), order: idx
      });
    });
    return out;
  }
  /* ---------- state ---------- */
  var ALL = [];
  var source = "";
  // plain-language run names (runinfo.js), rebuilt as the Scenes index and manifests arrive
  var MANS = {}, RI = RunInfo.build([], [], {});
  function refreshRI() { RI = RunInfo.build(ALL, scenesIdx && scenesIdx.runs, MANS); }
  var filt = { tests: false, capped: false, ended: false };
  var sort = { key: "overall", dir: -1 };
  var RUNS_SHOWN = 8, runsAll = false;

  function visible() {
    return ALL.filter(function (r) {
      if (!filt.tests && isTest(r)) return false;
      if (!filt.capped && isCapped(r)) return false;
      if (!filt.ended && isLive(r)) return false;
      return true;
    });
  }
  function realRows() { return ALL.filter(function (r) { return !isTest(r); }); }
  function rowByExp(name) {
    var hit = null; ALL.forEach(function (r) { if (r.exp === name && (!hit || (r.t || 0) > (hit.t || 0))) hit = r; });
    return hit;
  }

  /* ---------- badges ---------- */
  function badgesFor(r) {
    var b = el("div", { class: "badges" });
    if (r.ref) { b.appendChild(el("span", { class: "badge", text: "published, all 171 tasks" })); return b; }
    if (isLive(r)) b.appendChild(el("span", { class: "badge" + (isEnded(r) ? " warn" : ""),
      title: isStale(r) ? "Marked running at launch and never updated. Jobs stop after about 6 hours, so this run ended without a result." : "Status row from the experiment workflow. Not a score.",
      text: isStale(r) ? "! no result, stale" : r.status === "running" ? "running" : r.status === "generated" ? "generated, not scored" : "! " + r.status + ", no result" }));
    if (isTest(r)) b.appendChild(el("span", { class: "badge", title: "Produced by tests/fake_runner.py. Not a real model score.", text: "pipeline test" }));
    if (isOpen(r)) b.appendChild(el("span", { class: "badge warn", title: "Fixed action scripts from the dataset, no AI player. Used for A/B tests only, never for final scores.", text: "open loop, A/B only" }));
    else if (isScripted(r)) b.appendChild(el("span", { class: "badge warn", title: "The scripted player replayed the dataset moves chunk by chunk; no AI player chose them. For A/B of model-side changes only, never a final score.", text: "scripted moves, test only" }));
    else if (isClosed(r)) b.appendChild(el("span", { class: "badge ok", title: "An AI player chose every move while the world was being generated (closed loop).", text: "AI played" }));
    if (r.branch && r.branch !== "main") b.appendChild(el("span", { class: "badge warn", title: "Run from branch " + r.branch + ". The code behind this row is not merged into main yet.", text: "code not merged" }));
    if (isPartial(r)) b.appendChild(el("span", { class: "badge partial", title: "Fewer than all " + FULL_TASKS + " tasks. Not comparable to the full-benchmark paper numbers.", text: "partial" }));
    if (isCapped(r)) b.appendChild(el("span", { class: "badge warn", title: "Each rollout was cut short. A behaviour check, never comparable to a real score.",
      text: typeof r.max_chunks === "number" && r.max_chunks > 0 ? "capped smoke, " + r.max_chunks + " chunks" : "capped smoke" }));
    else if (isSmoke(r) && !isScripted(r)) b.appendChild(el("span", { class: "badge warn", title: "Fewer than " + DEV_TASKS + " tasks or scored only once: too small to estimate a score.", text: "tiny test run" }));
    return b;
  }

  /* ---------- runs table ---------- */
  // [key, label, class, numeric (sort desc first), short label for phones]
  var COLS = [
    ["exp", "What it tests", "exp", false, "What"],
    ["overall", "Overall", "num", true, "All"],
    ["gc", "GC", "num", true, "GC"], ["if", "IF", "num", true, "IF"],
    ["insight", "Insight", "num", true, "Ins"], ["outsight", "Out-of-sight", "num", true, "OoS"],
    ["n_tasks", "Tasks", "num hide-sm", true, ""], ["passes", "Passes", "num hide-sm", true, ""], ["t", "When (UTC)", "hide-sm", true, ""]
  ];
  function headLabel(c) {
    return c[4] && c[4] !== c[1] ? [el("span", { class: "long", text: c[1] }), el("span", { class: "short", "aria-hidden": "true", text: c[4] })] : [el("span", { text: c[1] })];
  }
  function rowEl(r) {
    var tr = el("tr", { class: r.ref ? "ref" : "" });
    var info = r.ref ? null : RI.get(r.exp);
    var td = el("td", { class: "exp" }, [el("div", { class: "nm", text: info ? info.short + " · " + info.size + " · " + info.driver : r.exp })]);
    if (info) td.appendChild(el("div", { class: "rawid", text: r.exp }));
    if (!r.ref) td.appendChild(el("div", { class: "meta-line hide-sm", text: [r.runner, r.split, r.branch].filter(Boolean).join(" · ") }));
    td.appendChild(badgesFor(r));
    if (r.notes && !r.ref) td.appendChild(el("div", { class: "meta-line notes hide-sm", title: r.notes, text: r.notes }));
    tr.appendChild(td);
    var o = el("td", { class: "num overall" });
    if (r.overall === null) dashCell(o);
    else {
      o.appendChild(el("div", { text: fmt(r.overall) }));
      if (typeof r.overall_std === "number") o.appendChild(el("div", { class: "std", text: "±" + fmt(r.overall_std) }));
    }
    tr.appendChild(o);
    FAMS.forEach(function (f) { var t = el("td", { class: "num" }); if (r[f[0]] === null) dashCell(t); else t.textContent = fmt(r[f[0]]); tr.appendChild(t); });
    var nt = el("td", { class: "num hide-sm" });
    if (r.ref) nt.textContent = String(FULL_TASKS);
    else if (r.n_tasks === null) dashCell(nt);
    else {
      nt.textContent = String(r.n_tasks);
      if (r.n_missing) nt.appendChild(el("div", { class: "std bad", text: r.n_missing + " missing" }));
      if (r.n_dropped) nt.appendChild(el("div", { class: "std bad", text: r.n_dropped + " unscored" }));
    }
    tr.appendChild(nt);
    var p = el("td", { class: "num hide-sm" }); if (r.passes === null || r.ref) dashCell(p); else p.textContent = String(r.passes); tr.appendChild(p);
    var tt = el("td", { class: "hide-sm" });
    if (r.ref) tt.appendChild(el("span", { class: "std", text: "paper" }));
    else {
      if (r.t !== null) tt.appendChild(el("div", { title: r.ts, text: fmtTime(r.t) })); else dashCell(tt);
      var links = el("div", { class: "std" });
      if (r.sha && /^[0-9a-f]{7,40}$/i.test(r.sha)) links.appendChild(el("a", { href: COMMIT + r.sha, target: "_blank", rel: "noopener", text: r.sha.slice(0, 7) }));
      if (r.run_url && /^https:\/\/github\.com\//.test(r.run_url)) { if (links.firstChild) links.appendChild(document.createTextNode(" · ")); links.appendChild(el("a", { href: r.run_url, target: "_blank", rel: "noopener", text: "job" })); }
      if (links.firstChild) tt.appendChild(links);
    }
    tr.appendChild(tt);
    return tr;
  }
  function sortVal(r, k) { var v = r[k]; return v === undefined || v === null || v === "" ? null : v; }
  function renderBoard() {
    var t = $("board"); clear(t);
    var hr = el("tr");
    COLS.forEach(function (c) {
      var th = el("th", { class: c[2], scope: "col", "aria-sort": sort.key === c[0] ? (sort.dir > 0 ? "ascending" : "descending") : "none" });
      var b = el("button", { type: "button", title: "Sort by " + c[1] }, headLabel(c).concat([el("span", { class: "arrow", "aria-hidden": "true", text: sort.key === c[0] ? (sort.dir > 0 ? "▲" : "▼") : "" })]));
      b.addEventListener("click", function () {
        if (sort.key === c[0]) sort.dir = -sort.dir; else { sort.key = c[0]; sort.dir = c[3] ? -1 : 1; }
        renderBoard(); syncUrl();
      });
      th.appendChild(b); hr.appendChild(th);
    });
    t.appendChild(el("thead", null, [hr]));
    var rows = visible().slice().sort(function (a, b) {
      // runs big enough to estimate a score first, tiny and scripted test runs after
      var sm = /^(overall|gc|if|insight|outsight)$/.test(sort.key) ? (isSmoke(a) ? 1 : 0) - (isSmoke(b) ? 1 : 0) : 0;
      if (sm) return sm;
      var x = sortVal(a, sort.key), y = sortVal(b, sort.key);
      if (x === null && y === null) return a.order - b.order;
      if (x === null) return 1; if (y === null) return -1;
      var c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return c * sort.dir || a.order - b.order;
    });
    var total = rows.length;
    if (!runsAll) rows = rows.slice(0, RUNS_SHOWN);
    var more = $("runs-more");
    if (more) { more.hidden = total <= RUNS_SHOWN; more.textContent = runsAll ? "Show the first " + RUNS_SHOWN + " only" : "Show all " + total + " runs"; }
    var tb = el("tbody");
    if (!rows.length) tb.appendChild(el("tr", null, [el("td", { class: "empty", colspan: String(COLS.length), text: ALL.length ? "No runs match. Tick a box above to show hidden rows." : "No runs logged yet." })]));
    rows.forEach(function (r) { tb.appendChild(rowEl(r)); });
    t.appendChild(tb);
    var rb = el("tbody");
    rb.appendChild(el("tr", { class: "refhead" }, [el("td", { colspan: String(COLS.length), text: "Published scores from the PlayWorld paper (all 171 tasks)" })]));
    REFS.forEach(function (r) { rb.appendChild(rowEl(r)); });
    t.appendChild(rb);
  }
  function renderToggles() {
    function count(id, pred) { var n = ALL.filter(pred).length; $(id).textContent = "(" + n + ")"; }
    count("capped-count", function (r) { return !isTest(r) && isCapped(r); });
    count("ended-count", function (r) { return !isTest(r) && !isCapped(r) && isLive(r); });
    count("tests-count", isTest);
    $("f-capped").checked = filt.capped; $("f-ended").checked = filt.ended; $("f-tests").checked = filt.tests;
  }

  /* ---------- headline ---------- */
  function isFull(r) { return r.split === "all" && r.n_tasks !== null && r.n_tasks >= FULL_TASKS; }
  // a final score: closed loop, all 171 tasks, 2+ passes, nothing missing or dropped, code on main, not capped
  function isFinal(r) {
    return !isCapped(r) && isClosed(r) && isFull(r) && r.passes !== null && r.passes >= 2 &&
      r.n_missing === 0 && r.n_dropped === 0 && r.branch === "main";
  }
  // best closed-loop run big enough to estimate a score (never capped, tiny or a pipeline test)
  function bestClosed() {
    var best = null;
    realRows().forEach(function (r) { if (isClosed(r) && !isSmoke(r) && r.overall !== null && (!best || r.overall > best.overall)) best = r; });
    return best;
  }
  function bestFinal() {
    var best = null;
    realRows().forEach(function (r) { if (isFinal(r) && r.overall !== null && (!best || r.overall > best.overall)) best = r; });
    return best;
  }
  // runs whose AI player differs from every run compared since
  var PLAYER_NOTE = { "lb14-session-agent-dev-v1": "Older AI player than later runs. Diagnostic only." };
  function renderStatus() {
    var box = $("status"), fin = bestFinal(), shown = fin || bestClosed();
    box.className = "scorecard card" + (fin && fin.overall - TARGET >= 2 * (fin.overall_std || FALLBACK_STD) ? " ok" : "");
    clear(box);
    box.appendChild(el("div", { class: "label", text: fin ? "Final score" : "Best official score so far" }));
    var big = el("div", { class: "big" }, [document.createTextNode(shown ? fmt(shown.overall) : "-")]);
    if (shown && shown.overall_std !== null) big.appendChild(el("span", { class: "pm", text: " ± " + fmt(shown.overall_std) }));
    box.appendChild(big);
    if (shown) {
      var b = el("div", { class: "badges" });
      function badge(cls, text) { b.appendChild(el("span", { class: "badge " + cls, text: text })); }
      badge(isFull(shown) ? "ok" : "warn", isFull(shown) ? "all 171 tasks" : shown.n_tasks + " of " + FULL_TASKS + " tasks");
      badge(isClosed(shown) ? "ok" : "warn", isClosed(shown) ? "AI played" : "open loop");
      badge(shown.passes >= 2 ? "ok" : "warn", shown.passes + " judge passes");
      if (shown.n_missing || shown.n_dropped) badge("bad", "tasks unscored"); else if (shown.n_missing === 0 && shown.n_dropped === 0) badge("ok", "every task scored");
      if (shown.branch && shown.branch !== "main") badge("warn", "code not merged");
      box.appendChild(b);
      box.appendChild(el("p", { class: "vs" }, [el("code", { class: "rawid", text: shown.exp })]));
      if (PLAYER_NOTE[shown.exp]) box.appendChild(el("p", { class: "vs", text: PLAYER_NOTE[shown.exp] }));
    } else box.appendChild(el("p", { class: "vs", text: "No run big enough to estimate a score yet (24 or more tasks, 2 or more judge passes)." }));
    var lb = REFS.filter(function (r) { return r.exp === "LingBot-World2"; })[0];
    box.appendChild(el("p", { class: "vs", text: "Paper, 171 tasks: Genie 3 " + fmt(GENIE.overall) + ", LingBot-World v2 " + fmt(lb.overall) + "." }));
  }
  // starting model against method on all 171 tasks. Hidden until a closed-loop, uncapped, 171-task run with 2+ passes is scored.
  // The starting model is the full run with no method flags; the method is the best other full run.
  function fullRuns() {
    var rows = realRows().filter(function (r) { return isFull(r) && isClosed(r) && !isCapped(r) && r.overall !== null && r.passes !== null && r.passes >= 2; });
    // a run whose flags are not recorded is neither: it is counted and named in the note, never shown as starting model or method
    var start = null, method = null, unknown = [];
    rows.forEach(function (r) {
      var ri = RI.get(r.exp), w = ri && ri.words;
      if (!w) { unknown.push(r.exp); return; }
      if (w.length === 0) { if (!start || r.t > start.t) start = r; } else if (!method || r.overall > method.overall) method = r;
    });
    return { start: start, method: method, unknown: unknown, any: rows.length > 0 };
  }
  // tasks left out of a run's mean: clips never generated (counted as 1.0 by the report) and results the verifier could not use (dropped)
  function leftOut(r) { return (r.n_missing || 0) + (r.n_dropped || 0);
  }
  function renderFullResult() {
    var box = $("fullres"); if (!box) return; clear(box);
    var f = fullRuns(); if (!f.start && !f.method) { box.hidden = true; return; }
    box.hidden = false;
    var lb = REFS.filter(function (r) { return r.exp === "LingBot-World2"; })[0];
    var cols = [["Genie 3, paper", GENIE], ["LingBot v2, paper", lb]];
    if (f.start) cols.push(["Starting model, ours", f.start]);
    if (f.method) cols.push(["Method, ours", f.method]);
    var hr = el("tr", null, [el("th", { scope: "col", text: "Task type" })].concat(cols.map(function (c) { return el("th", { class: "num", scope: "col", text: c[0] }); })));
    if (f.start && f.method) hr.appendChild(el("th", { class: "num", scope: "col", text: "Change" }));
    var tb = el("tbody");
    FAMS.map(function (x) { return [x[0], FAMINFO[x[0]].name]; }).concat([["overall", "Overall"]]).forEach(function (k) {
      var tr = el("tr", { class: k[0] === "overall" ? "total" : "" }, [el("th", { scope: "row", text: k[1] })]);
      cols.forEach(function (c) { var td = el("td", { class: "num" }); if (c[1][k[0]] === null || c[1][k[0]] === undefined) dashCell(td); else td.textContent = fmt(c[1][k[0]]); tr.appendChild(td); });
      if (f.start && f.method) {
        var a = f.start[k[0]], b2 = f.method[k[0]], td2 = el("td", { class: "num" });
        if (typeof a !== "number" || typeof b2 !== "number") dashCell(td2);
        else { var d = b2 - a; td2.appendChild(el("span", { class: d > 0 ? "good" : d < 0 ? "bad" : "", text: (d > 0 ? "+" : "") + fmt(d) })); }
        tr.appendChild(td2);
      }
      tb.appendChild(tr);
    });
    var complete = [f.start, f.method].every(function (r) { return !r || leftOut(r) === 0; });
    box.appendChild(el("h2", { text: complete ? "All 171 tasks, AI played" : "171-task runs, AI played, not every task scored" }));
    box.appendChild(el("div", { class: "scroll" }, [el("table", { class: "fullres" }, [el("thead", null, [hr]), tb])]));
    var note = [];
    [["Starting model", f.start], ["Method", f.method]].forEach(function (x) {
      var r = x[1]; if (!r) return;
      note.push(x[0] + " " + r.exp + ": " + fmt(r.overall) + (typeof r.overall_std === "number" ? " ± " + fmt(r.overall_std) : "") + ", " + r.passes + " passes" + (r.n_missing ? ", " + r.n_missing + " clips missing and counted as 1.0" : "") +
        (r.n_dropped ? ", " + r.n_dropped + " tasks dropped from the mean" : "") + ".");
    });
    if (f.unknown.length) note.push("Not shown, flags not recorded: " + f.unknown.join(", ") + ".");
    if (!complete) note.push("A run with tasks left out is not comparable with the paper rows.");
    if (f.start && f.method) {
      var d2 = f.method.overall - f.start.overall, sd = Math.max(f.start.overall_std || FALLBACK_STD, f.method.overall_std || FALLBACK_STD);
      note.push("The overall change is " + (Math.abs(d2) >= 2 * sd ? "larger" : "smaller") + " than twice the pass spread (" + fmt(2 * sd) + ")" + (Math.abs(d2) >= 2 * sd ? "." : ", so it is inside the noise."));
    }
    box.appendChild(el("p", { class: "note", text: note.join(" ") }));
  }
  function renderFull() {
    var full = realRows().filter(function (r) { return isFull(r) && r.overall !== null; });
    var most = 0; realRows().forEach(function (r) { if (r.overall !== null && r.n_tasks > most) most = r.n_tasks; });
    $("full").textContent = full.length ? "" : "No " + FULL_TASKS + "-task score yet. Scored runs cover at most " + most + " tasks, so none compares directly with the paper rows.";
    $("full").hidden = !!full.length;
  }
  function renderRuler() {
    var host = $("ruler"); clear(host);
    var W = Math.max(300, host.clientWidth || 700), narrow = W < 520, H = narrow ? 150 : 124;
    var m = { l: 14, r: 14 };
    var fin = bestFinal(), ours = fin || bestClosed();
    var hi = Math.max(3, ours ? Math.ceil((ours.overall + 0.3) * 2) / 2 : 3);
    var x = function (v) { return m.l + ((v - 1) / (hi - 1)) * (W - m.l - m.r); };
    var axisY = narrow ? 80 : 64;
    var svg = sv("svg", { viewBox: "0 0 " + W + " " + H, role: "img",
      "aria-label": "Overall score on a 1 to " + hi + " axis. " + REFS.map(function (r) { return r.exp + " " + fmt(r.overall); }).join(", ") +
        (ours ? ". Ours " + fmt(ours.overall) + (fin ? "" : " (partial)") : ". Ours: not yet scored") });
    svg.appendChild(sv("rect", { x: x(1), y: axisY - 3, width: x(TARGET) - x(1), height: 6, rx: 3, fill: "var(--wash)" }));
    svg.appendChild(sv("rect", { x: x(TARGET), y: axisY - 3, width: x(hi) - x(TARGET), height: 6, rx: 3, fill: "var(--good)", opacity: 0.18 }));
    svg.appendChild(sv("line", { x1: x(1), x2: x(hi), y1: axisY, y2: axisY, stroke: "var(--axis)" }));
    var oursX = ours ? x(ours.overall) : -1e9;
    for (var t = 1; t <= hi + 1e-9; t += 0.5) {
      svg.appendChild(sv("line", { x1: x(t), x2: x(t), y1: axisY + 4, y2: axisY + 9, stroke: "var(--axis)" }));
      if (Math.abs(x(t) - oursX) > 16) svg.appendChild(sv("text", { x: x(t), y: axisY + 22, "text-anchor": t === 1 ? "start" : (t >= hi ? "end" : "middle"), text: t.toFixed(1) }));
    }
    svg.appendChild(sv("text", { x: x(hi), y: axisY - 10, "text-anchor": "end", style: "fill:var(--good)", text: "above Genie 3" }));
    var refs = REFS.slice().sort(function (a, b) { return a.overall - b.overall; });
    refs.forEach(function (r, i) {
      var cx = x(r.overall), ly = narrow ? axisY - 12 - i * 15 : axisY - 14 - (i % 2) * 18;
      var isG = r === GENIE;
      svg.appendChild(sv("line", { x1: cx, x2: cx, y1: ly + 3, y2: axisY - 5, stroke: isG ? "var(--ink)" : "var(--axis)", "stroke-dasharray": isG ? null : "2 2" }));
      svg.appendChild(sv("circle", { cx: cx, cy: axisY, r: isG ? 6 : 4.5, fill: isG ? "var(--ink)" : "var(--ref)" }));
      var anchor = cx < 80 ? "start" : (cx > W - 80 ? "end" : "middle");
      svg.appendChild(sv("text", { class: isG ? "lab" : "", x: cx, y: ly, "text-anchor": anchor, text: (narrow ? ({ "Matrix-Game-3.0": "MG-3.0", "LingBot-World2": "LingBot", "SANA-WM": "SANA" }[r.exp] || r.exp) : r.exp) + " " + fmt(r.overall) }));
    });
    if (ours) {
      var ox = x(ours.overall), partial = !fin, oy = axisY + (narrow ? 50 : 40);
      svg.appendChild(sv("line", { x1: ox, x2: ox, y1: axisY + 6, y2: oy - 12, stroke: "var(--s1)", "stroke-width": 2 }));
      svg.appendChild(sv("circle", { cx: ox, cy: axisY, r: 7, fill: partial ? "var(--surface)" : "var(--s1)", stroke: "var(--s1)", "stroke-width": 2.5 }));
      var an = ox < 120 ? "start" : (ox > W - 120 ? "end" : "middle");
      svg.appendChild(sv("text", { class: "lab", x: ox, y: oy, "text-anchor": an, style: "fill:var(--s1)",
        text: "Ours " + fmt(ours.overall) + (partial ? " (" + ours.n_tasks + " tasks, partial)" : "") }));
    }
    host.appendChild(svg);
  }
  // compact family table: paper rows next to the headline run
  function renderFams() {
    var t = $("fams"); if (!t) return; clear(t);
    var b = bestFinal() || bestClosed();
    var lb = REFS.filter(function (r) { return r.exp === "LingBot-World2"; })[0];
    var hr = el("tr");
    [["Task type", "Task type", "exp"], ["Genie 3", "G3", "num"], ["LingBot v2", "LB", "num"],
     [b ? "Ours (" + b.n_tasks + " tasks)" : "Ours", "Ours", "num"]].forEach(function (h) {
      hr.appendChild(el("th", { class: h[2], scope: "col" }, headLabel([0, h[0], 0, 0, h[1]])));
    });
    t.appendChild(el("thead", null, [hr]));
    var tb = el("tbody");
    FAMS.forEach(function (f) {
      var k = f[0], info = FAMINFO[k], tr = el("tr");
      tr.appendChild(el("td", { class: "exp" }, [el("span", { class: "nm", text: info.name }), el("span", { class: "meta-line q", text: " " + info.q })]));
      tr.appendChild(el("td", { class: "num", text: fmt(GENIE[k]) }));
      tr.appendChild(el("td", { class: "num", text: fmt(lb[k]) }));
      var o = el("td", { class: "num" }); if (b && b[k] !== null) o.textContent = fmt(b[k]); else dashCell(o); tr.appendChild(o);
      tb.appendChild(tr);
    });
    t.appendChild(tb);
  }

  /* ---------- story content (edit here as work lands) ---------- */
  var PR = "https://github.com/" + REPO + "/pull/";
  var FAMINFO = {
    gc: { name: "Geometry consistency", q: "layout holds as the camera moves", ask: "Move the camera away and back. Is the place still the same place?" },
    if: { name: "Interaction fidelity", q: "each action does what was asked", ask: "Press a key. Does the subject do what was asked, with real contact?" },
    insight: { name: "Insight evolution", q: "an on-screen process keeps going", ask: "Wait and watch. Does a process on screen keep going sensibly?" },
    outsight: { name: "Out-of-sight evolution", q: "hidden things change sensibly", ask: "Look away, then back. Did the hidden part of the world move on sensibly?" }
  };
  // group: now (model-side A/B) | parked (player-side, tried) | cand (merged or proposed, unscored)
  // arms: [label, exp] pairs read from results/experiments.csv; the first is the control. cells: per-task readout from results/reports/.
  // pending: shown while not every arm has a score (the CSV says "failed" for an arm whose clips exist but whose scoring failed).
  var METHODS = [
    { group: "now", title: "Turn calibration", arms: [["off", "fx14-model-dev-v2-a1"], ["on", "fx14-model-dev-v2-a2"]],
      cells: "of 15 tasks scored in both arms, 0 up a full point and 1 down; 8 and 9 of 24 clips missing and counted as 1.0",
      body: "One turn key turns the angle the task prompt names (22.5 degrees sideways, 20 up or down) instead of the default 34 and 11. The same comparison on the 6 GC tasks alone (orc14-gc-v1) moved 2 tasks up a full point and none down, and the GC mean from 2.18 to 2.58, inside the noise. GC031 gained 1.95 there and 0.35 here, and its 4.00 there comes with a judge comment that the camera never completes the 360-degree turn. The gain did not replicate, so turn calibration is not adopted.",
      also: ["orc14-gc-v1-a1", "orc14-gc-v1-a2"], links: [["#23", PR + "23"]] },
    { group: "now", title: "Caption prompt", arms: [["off", "fx14-model-dev-v2-a2"], ["on", "fx14-model-dev-v2-a3"]], also: ["ins14-base-v2", "ins14-caption-v1"],
      cells: "of 14 tasks scored in both arms, 2 up a full point and 2 down; no insight clip in either arm",
      body: "Conditions the model on the task's scene caption instead of the player goal, which reads \"wait and observe\" on 29 of 30 insight tasks. It was aimed at insight, and these runs have no insight clips: every insight task ran out of memory in the decode step, fixed since (#120). Earlier ins14 runs: the control ins14-base-v2 was generated and not scored, and the caption arm ins14-caption-v1 was cancelled.",
      links: [["#32", PR + "32"], ["#63", PR + "63"], ["#120", PR + "120"]] },
    { group: "now", title: "Insight director, IF slow translation (re-anchor on, cannot fire with fixed actions)", arms: [["without", "fx14-model-dev-v2-a3"], ["with", "fx14-model-dev-v2-a4"]],
      cells: "of 11 tasks scored in both arms, 1 up a full point and 0 down; no insight clip in either arm, 10 and 13 of 24 clips missing",
      body: "Adds an insight prompt cue and half-speed camera translation on IF tasks, on top of the caption prompt. The one task that moved a full point is a GC task (GC031), which none of the added flags should change with fixed actions, so that move is unexplained. Re-anchoring is switched on in the second arm, but fixed action scripts replay each task as one call, so it never fires there; its test is the scripted-player GC A/B below.",
      links: [["#46", PR + "46"], ["#90", PR + "90"]] },
    { group: "now", title: "Conditioning strength per denoising step", arms: [["control", "cs14-fx-v1-a1"], ["schedule", "cs14-fx-v1-a2"], ["+ text 1.0", "cs14-fx-v1-a3"], ["early 4", "cs14-fx-v1-a4"]],
      cells: "3 of 7 tasks scored, all 4 insight clips missing and counted as 1.0; the GC task lost a full point in 2 of 3 schedule arms, the 2 IF tasks gained less than a point",
      body: "Scales camera and text conditioning on the early denoising steps of stationary and third-person chunks and restores it on the late steps. All four arms have the caption prompt and turn calibration on. On insight tasks (dec14-ins-v1, OE001 and OE018, after the decode fix) the schedule lowered both: 3.00 to 1.50 overall. Dropped.",
      links: [["#101", PR + "101"]] },
    { group: "now", title: "Attention window", arms: [["control", "mem14-fx-v1-a1"], ["sink 12", "mem14-fx-v1-a2"], ["local 36", "mem14-fx-v1-a3"], ["both", "mem14-fx-v1-a4"]],
      pending: "control and sink 12 scored (2.35, 2.17); the two arms with a window of 36 failed",
      also: ["pm14-fx-v1-a3", "pm14-fx-v2-a4", "win14-fx-v1-a3", "win14-fx-v1-a4"],
      body: "Changes how many latent frames the model keeps attending to (a sink of 6 opening latents in an attention window of 18 by default), which sets how far back it remembers. Run on the 6 out-of-sight dev tasks and 3 GC tasks. OE039 scored about 3 in all three arms that keep more of the opening view: 3.00 with a sink of 12, and 3.12 in both arms with a sink of 10 in a window of 22 (pm14-fx-v1-a3, pm14-fx-v2-a4), against 1.25 to 2.00 across the control's scorings. The two 10 and 22 arms scored 2.25 and 2.67 on out-of-sight, about 2.46 against 1.83 to 2.10 for control. That is at the noise bar, on one seed. Their two videos are nearly identical, yet they scored 1.50 and 2.88 on OE048. A sink of 12 alone showed no out-of-sight gain (1.86 against 1.93) and dropped OE048 from 3.19 to 1.25. A second seed is running (win14-fx-v1). The two arms with an attention window of 36 produced no clips.",
      links: [["#104", PR + "104"]] },
    { group: "now", title: "Sink key scale", arms: [["control", "sks14-fx-v1-a1"], ["0.7", "sks14-fx-v1-a2"], ["0.4", "sks14-fx-v1-a3"], ["0.7 from chunk 4", "sks14-fx-v1-a4"]],
      cells: "every scaled arm is lower than the control; dropped",
      body: "Lowers how strongly later chunks attend to the pinned opening frames (the sink), to test whether those frames pull a returning camera back to the scene as it was at the start. 6 out-of-sight dev tasks, fixed action scripts. A weaker sink lowered out-of-sight from 2.10 to between 1.25 and 1.65. That fits the reading that the sink is what lets the camera return to the start view.",
      links: [["#112", PR + "112"]] },
    { group: "now", title: "Insight prompt: goal, caption, or caption with the insight director", arms: [["goal prompt", "ins14-fx-v2-a1"], ["caption", "ins14-fx-v2-a2"], ["caption and director", "ins14-fx-v2-a3"]],
      body: "Runs on all six insight dev tasks. Insight tasks are wait-only, so the rollout with fixed action scripts is the same as the closed-loop one.",
      links: [["#32", PR + "32"], ["#90", PR + "90"]] },
    { group: "now", title: "GC chunk-level flags (scripted player)", arms: [["control", "sp14-gc-v1-a1"], ["chunk director", "sp14-gc-v1-a2"], ["ease turns", "sp14-gc-v1-a3"], ["re-anchor", "sp14-gc-v1-a4"]],
      cells: "chunk director lowered 2 of 6 tasks by a full point and raised none; ease turns moved none; re-anchor raised 1 (GC033) and lowered none; one seed",
      body: "The scripted player replays the dataset moves chunk by chunk, so flags that act per chunk can fire. 6 GC dev tasks, caption prompt and turn calibration in all arms. The chunk director and turn easing were dropped as harmful or null on a repeat measurement; re-anchor is a weak lead. Not a closed-loop score.",
      links: [["#100", PR + "100"], ["#102", PR + "102"]] },
    { group: "now", title: "Pose-indexed memory", arms: [["control", "pm14-fx-v1-a1"], ["memory", "pm14-fx-v1-a2"], ["memory + window", "pm14-fx-v1-a3"]],
      cells: "6 tasks, one seed; the first run changed no frame, so any difference is judge spread",
      body: "Re-inserts past views into the attention sink when the camera returns near them. Every memory arm so far (pm14-fx-v1-a2, pm14-fx-v2-a1, pm14-fx-v2-a2) made zero retrievals, and its clips are byte-identical to control, so its scores are the control plus judge spread. A fix is in progress. Not a result.",
      also: ["pm14-fx-v2-a1", "pm14-fx-v2-a2", "pm14-fx-v2-a3", "pm14-fx-v2-a4"], links: [["#123", PR + "123"]] },
    { group: "parked", title: "Return stop", arms: [["off", "rs13-arms-v1-a1"], ["on", "rs13-arms-v1-a2"]], cells: "2 of 3 GC tasks up a full point, 0 of 3 out-of-sight",
      body: "Ends the rollout once the commanded camera has left and come back to the start. 1.3B model, one run per side, player hint and turn calibration on in both.",
      links: [["#75", PR + "75"]] },
    { group: "parked", title: "GC completion hint", arms: [["off", "gch13-arms-v1-a1"], ["on", "gch13-arms-v1-a2"]], cells: "2 of 3 tasks down a full point",
      body: "Tells the player to run the camera path once and end. 1.3B model, one run per side. It ran before the player's empty-reply fix (#89).",
      links: [["#78", PR + "78"], ["#89", PR + "89"]] },
    { group: "parked", title: "Player hint", arms: [["no flags", "smk14-arms-gc-v2-a1"], ["turn cal + hint", "smk14-arms-gc-v2-a2"]],
      body: "Tells the player how far one action turns the camera and where the commanded camera is. Turn calibration is also on in the second arm. Only capped smoke runs exist, which never count as scores.",
      links: [["#59", PR + "59"]] },
    { group: "cand", title: "Camera-conditioning weight modulation, IF identity cue",
      body: "Weight modulation scales how strongly the model follows the camera command, per chunk; the identity cue adds a sentence about keeping each subject's identity on third-person IF tasks. Both fixed-action runs (wm14-fx-v1, wm14-fx-a100-v1) were cancelled before finishing; only a capped smoke check of weight modulation exists.",
      also: ["wm14-arm-c10-v1"], links: [["#87", PR + "87"], ["#104", PR + "104"]] },
    { group: "cand", title: "Proposal batch 2: IF horizon, IF camera hint, history endpoints, IF repeat check",
      body: "Merged behind opt-in flags. Its insight director and IF slow translation are in the model-side runs above.", links: [["#90", PR + "90"]] },
    { group: "cand", title: "Proposal batch 3: IF subject director",
      body: "Merged behind opt-in flags. The batch's GC chunk director and GC ease turns are in the scripted-player GC A/B above.", links: [["#100", PR + "100"]] },
    { group: "cand", title: "Proposal batch 4: weight-modulation knobs, measured turn",
      body: "Merged behind opt-in flags and not run yet. The attention window is under test above.", links: [["#104", PR + "104"]] },
    { group: "cand", title: "Camera rates: turn step, yaw gain",
      body: "Turn step sets how many degrees one closed-loop turn covers, so an out-and-back fits inside the model's attention window. Yaw gain scales the yaw sent to the model. Merged behind opt-in flags and not run yet.", links: [["#105", PR + "105"], ["#119", PR + "119"]] },
    { group: "cand", title: "Sampling: noise mean coupling, noisy KV writes, early-step self-guidance",
      body: "Three changes to how each chunk is sampled or written to the model's memory. Merged behind opt-in flags and not run yet.", links: [["#103", PR + "103"], ["#112", PR + "112"]] }
  ];
  var GROUPS = [
    ["now", "Testing now: model-side", "Fixed moves (no AI player), 14B, official judge, 2 to 4 passes, one run per arm. Overall figures count a missing clip as 1.0, so read the per-task counts."],
    ["parked", "Tried and parked: player-side", "AI player, official judge, 4 passes, small task sets. None adopted."],
    ["cand", "Candidates, not yet scored", "Off by default. Not results."]
  ];
  function rowText(r) {
    if (!r) return "not logged";
    if (r.overall !== null && !isCapped(r)) return fmt(r.overall) + " on " + r.n_tasks + " task" + (r.n_tasks === 1 ? "" : "s") + ", " + r.passes + " passes";
    if (isCapped(r)) return "capped smoke" + (r.status ? ", " + r.status : "");
    return isStale(r) ? "no result" : (r.status || "no score");
  }
  function armsResult(m) {
    if (!m.arms) return { text: "not scored", none: true };
    var rows = m.arms.map(function (a) { return rowByExp(a[1]); });
    if (rows.every(function (r) { return r && r.overall !== null && !isCapped(r); })) {
      var s = m.arms.map(function (a, i) { return a[0] + " " + fmt(rows[i].overall); }).join(", ") + (rows.length === 2 ? " overall on " + rows[1].n_tasks + " tasks" : "");
      return { text: s + (m.cells ? "; " + m.cells : ""), none: false };
    }
    if (rows.some(function (r) { return r && isCapped(r); })) return { text: "capped smoke only, no decision", none: true };
    if (m.pending) return { text: m.pending, none: true };
    if (rows.some(function (r) { return r && r.status === "running" && !isStale(r); })) return { text: "running", none: true, run: true };
    if (rows.some(function (r) { return r && r.status === "generated"; })) return { text: "generated, not scored", none: true };
    if (rows.some(function (r) { return r && isEnded(r); })) return { text: "no result yet", none: true };
    return { text: "not scored", none: true };
  }
  function renderMethods() {
    var box = $("methods"); clear(box);
    GROUPS.forEach(function (g) {
      var items = METHODS.filter(function (m) { return m.group === g[0]; });
      if (!items.length) return;
      box.appendChild(el("h3", { class: "mgroup", text: g[1] }));
      box.appendChild(el("p", { class: "mnote", text: g[2] }));
      var ul = el("ul", { class: "mlist" });
      items.forEach(function (m) {
        var res = armsResult(m);
        var summary = el("summary", null, [el("span", { class: "nm", text: m.title }),
          el("span", { class: "res" + (res.none ? " none" : "") + (res.run ? " run" : ""), text: res.text })]);
        var body = el("div", { class: "more" }, [el("p", { text: m.body })]);
        var exps = (m.arms || []).map(function (a) { return [a[0], a[1]]; }).concat((m.also || []).map(function (e) { return ["", e]; }));
        if (exps.length) body.appendChild(el("p", { class: "std", text: "Runs: " + exps.map(function (a) { var ri = RI.get(a[1]); return (ri && ri.armLabel ? ri.armLabel : a[0] || "run") + " (" + a[1] + "): " + rowText(rowByExp(a[1])); }).join("; ") + "." }));
        var links = el("p", { class: "links" });
        m.links.forEach(function (l) {
          links.appendChild(l[1].charAt(0) === "#" ? el("a", { href: l[1], text: "See " + l[0] }) : el("a", { href: l[1], target: "_blank", rel: "noopener", text: "PR " + l[0] }));
        });
        body.appendChild(links);
        ul.appendChild(el("li", null, [el("details", null, [summary, body])]));
      });
      box.appendChild(ul);
    });
  }

  /* ---------- story: findings in order, each with its evidence read live (edit here as work lands) ---------- */
  var BLOB = "https://github.com/" + REPO + "/blob/main/";
  // kind "ab" (default): ctl against arms [short label, exp, long label]; kind "repeat": the same settings run several times;
  // kind "note": text and a scene only. watch: { task, b: control, c: treatment } for the compare player; scene: [exp, task].
  // say: the one line the tour bar shows. Every number in body or say must be in results/ or research/.
  var STORY = [
    { id: "examples", kind: "gallery", title: "What works and what breaks, by task type",
      say: "For each task type, the rollout the judge scored highest and the one it scored lowest." },
    { id: "player", kind: "note", title: "The AI player decides most camera tasks",
      body: "In the 24-task baseline the AI player reversed direction 9 to 17 times per out-of-sight task and 25 times on GC036. On 4 of 6 out-of-sight tasks the camera never returned, so the judge had nothing to grade. Model-side tests therefore use fixed moves.",
      say: "The baseline player turned left and right for the whole rollout.",
      scene: ["lb14-session-agent-dev-v1", "GC036"], sceneLabel: "Watch GC036",
      links: [["baseline census", BLOB + "research/baseline-census.md"]] },
    { id: "noise", short: true, kind: "repeat", title: "Same video, three scorings, different scores",
      body: "Three controls with identical settings produce the same video. Their 4-pass means still differ, so a task counts as moved only at a full point, repeated on a second seed.",
      say: "Identical controls disagree. The bar is a full point, twice.",
      runs: [["run 1", "pm14-fx-v1-a1"], ["run 2", "sks14-fx-v1-a1"], ["run 3", "mem14-fx-v1-a1"]],
      watch: { task: "OE047", b: "pm14-fx-v1-a1", c: "sks14-fx-v1-a1" } },
    { id: "turncal", prs: [23], label: "Turn calibration", verdict: "not adopted", title: "Calibrated turns lifted two GC tasks, once",
      body: "Task prompts name 22.5 degrees per turn key; the model's default turns 34. With the rate calibrated, GC031 and GC036 gained more than a point, though the judge's comment on GC031 says the camera never completes its 360. On a second run they gained 0.35 and 0.80. Not adopted.",
      say: "Two tasks up on one run, under the bar on the second.",
      ctl: "orc14-gc-v1-a1", arms: [["turn cal", "orc14-gc-v1-a2", "turn calibration"]],
      watch: { task: "GC031", b: "orc14-gc-v1-a1", c: "orc14-gc-v1-a2" } },
    { id: "memory", prs: [123, 129], label: "Pose memory", verdict: "no result, rerun pending", kind: "repeat", title: "Pose memory never fired, and the score still moved",
      body: "Pose memory re-inserts an earlier view when the camera returns to it. In its first run it inserted nothing and the clips are byte-identical to control, yet GC036 moved 1.3 points and failed a gate. The two later memory arms also made zero retrievals. A fix is merged (PR #129) and its run is not scored yet.",
      say: "Our memory never fired. The flag counters caught it; the scores would have looked like an effect.",
      runs: [["control", "pm14-fx-v1-a1"], ["memory on", "pm14-fx-v1-a2"]], cap: "Both columns score the same video.",
      watch: { task: "GC036", b: "pm14-fx-v1-a1", c: "pm14-fx-v1-a2" } },
    { id: "sink", short: true, prs: [112], label: "Sink key scale", verdict: "dropped", title: "Turning down the opening frames made out-of-sight worse",
      body: "We expected the pinned opening frames to reset the scene when the camera returns. Turning their attention down lowered every arm, so returns appear to depend on them. Dropped.",
      say: "A hypothesis that failed. Every arm scored below control.",
      ctl: "sks14-fx-v1-a1", arms: [["0.7", "sks14-fx-v1-a2", "key scale 0.7"], ["0.4", "sks14-fx-v1-a3", "key scale 0.4"], ["0.7 early", "sks14-fx-v1-a4", "key scale 0.7 from chunk 4"]],
      watch: { task: "OE048", b: "sks14-fx-v1-a1", c: "sks14-fx-v1-a4" } },
    { id: "insight", prs: [32, 90], label: "Caption prompt on insight", verdict: "not adopted", title: "The scene caption alone did not move insight",
      body: "Insight tasks prompt the model with \"wait and observe\", and four of six baseline rollouts were flagged static or near static in a judge pass. Prompting with the scene caption moved no task by a full point. Adding the insight director, a fixed sentence about the activity, moved one task up and one down.",
      say: "Swapping \"wait and observe\" for the scene caption moved nothing by a full point.",
      ctl: "ins14-fx-v2-a1", arms: [["caption", "ins14-fx-v2-a2", "caption prompt"], ["+ cue", "ins14-fx-v2-a3", "caption prompt and insight director"]],
      watch: { task: "OE018", b: "ins14-fx-v2-a1", c: "ins14-fx-v2-a3" } },
    { id: "window", short: true, seeds: 2, prs: [104], label: "Larger attention window, two seeds", verdict: "not repeated", title: "A larger attention window moved different tasks on each seed",
      body: "At seed 1 it raised OE039 by 2.4 and OE069 by 1.0 and lowered nothing by a full point. At seed 0 the same flags raised GC031 by 1.65, lowered OE048 by 1.06 and left OE039 inside the control's spread. No task moved on both seeds.",
      say: "Our best lead, repeated on a second seed. Different tasks moved each time.",
      ctl: "win14-fx-v1-a3", arms: [["window", "win14-fx-v1-a4", "sink 10, window 22, seed 1"]], cap: "Seed 1. Judge's mean per task. ▲ ▼ a full point against control. Click a number to play that pair here.",
      watch: { task: "OE039", b: "win14-fx-v1-a3", c: "win14-fx-v1-a4" } },
    { id: "stack", label: "The stack, 24 tasks, two seeds", verdict: "running", pending: true, title: "The stack on all 24 dev tasks, at two seeds",
      body: "Turn calibration, caption prompt, insight director, slow IF translation and the larger attention window together, against no flags, on every dev task at two seeds.",
      say: "The combined method on all 24 dev tasks at two seeds is running now.",
      ctl: "stk14-fx-dev-v1-a1", arms: [["stack", "stk14-fx-dev-v1-a2", "the stack, seed 0"]],
      watch: { task: "OE039", b: "stk14-fx-dev-v1-a1", c: "stk14-fx-dev-v1-a2" } },
    { id: "open", short: true, kind: "note", title: "Still open",
      say: "No 171-task score yet, and nothing has repeated on two seeds.",
      points: ["No 171-task score, for the starting model or for a method.",
        "Every A/B here uses fixed moves, and all but one ran on a single seed. Adoption needs the AI player and two seeds.",
        "Dropped: conditioning schedule, sink key scale, GC chunk director, GC turn easing, GC completion hint.",
        "Leads: a larger attention window (moves tasks, not the same ones twice), the insight director (one up, one down), re-anchoring on GC (weak).",
        "Pose memory has no result yet."],
      links: [["status", BLOB + "AGENTS.md#status-against-the-timeline"]] }
  ];
  // changes adopted under the two-seed rule; shown in the verdict line under the lede
  var ADOPTED = [];
  var MOVE = 1.0;
  function tasksOfRun(exp) {
    var m = MANS[exp]; if (!m || m.scored === false) return null;
    var o = {}; (m.tasks || []).forEach(function (t) { o[t.task_id] = t; });
    return o;
  }
  // a task's pass-mean, or null when the run has no judged clip for it (missing rollouts carry a placeholder 1.0)
  function cellVal(t) {
    if (!t || typeof t.mean !== "number") return null;
    return (t.status || []).indexOf("missing") >= 0 ? null : t.mean;
  }
  function gateFail(t) { return !!t && (t.status || []).indexOf("gate_fail") >= 0; }
  // the other watch mode's deep-link params would win on reload, so drop them
  function dropParams(keys) {
    try {
      var q = new URLSearchParams(location.search); keys.forEach(function (k) { q.delete(k); });
      var qs = q.toString(); history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
    } catch (e) { /* sandboxed */ }
  }
  function watch(sel) {
    setMode("compare", false); dropParams(["scenes", "scene"]);
    document.dispatchEvent(new CustomEvent("pwa:compare", { detail: { task: sel.task, b: sel.b, c: sel.c, play: true } }));
    scrollToEl($("compare-clips"));
  }
  function openScene(exp, task) {
    scenesExp = exp; scenesTask = task; scenesWanted = ""; scenesScrolled = true;
    setMode("scenes", false); dropParams(["compare", "a", "b", "c"]);
    var req = scenesReq + 1;
    loadManifest().then(function () { if (req === scenesReq) { renderScenes(); syncUrl(); } });
    scrollToEl($("scenes"));
  }
  function scrollToEl(node) {
    if (!node || !node.scrollIntoView) return;
    var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    node.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
  }
  // clips play inside the finding's own card: one clip, or control and treatment started together and restarted together
  function taskOf(exp, task) { var m = MANS[exp]; return m ? (m.tasks || []).filter(function (t) { return t.task_id === task; })[0] || null : null; }
  // closing a player also cancels its pending start, so a closed player never begins playing detached videos
  var inlineStop = null;
  function watchSel(s) {
    if (s.kind !== "repeat") return s.watch;
    function lab(exp) { var r = s.runs.filter(function (x) { return x[1] === exp; })[0]; return r ? r[0] : exp; }
    return { task: s.watch.task, b: s.watch.b, c: s.watch.c, roles: [lab(s.watch.b), lab(s.watch.c)] };
  }
  function closeInline() {
    if (inlineStop) { inlineStop(); inlineStop = null; }
    // a single clip plays in its poster's place: take it out and put the poster back
    Array.prototype.forEach.call(document.querySelectorAll(".st-inplace"), function (n) {
      Array.prototype.forEach.call(n.querySelectorAll("video"), function (v) { v.pause(); });
      var poster = n.parentNode.querySelector(".st-poster"); if (poster) poster.hidden = false;
      n.parentNode.removeChild(n);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".st-play"), function (n) {
      Array.prototype.forEach.call(n.querySelectorAll("video"), function (v) { v.pause(); });
      n.parentNode.removeChild(n);
    });
  }
  function playIn(id, sel) {
    var li = $("story-" + id); if (!li) return;
    // sel.roles names the two clips when they are not a control and a treatment (the same settings run twice)
    var pairs = [[sel.b, sel.roles ? sel.roles[0] : sel.c ? "Control" : ""], [sel.c, sel.roles ? sel.roles[1] : "Treatment"]].filter(function (p) { return p[0]; })
      .map(function (p) { return { exp: p[0], role: p[1], t: taskOf(p[0], sel.task) }; }).filter(function (p) { return p.t && p.t.video; });
    if (!pairs.length) { if (sel.c) watch(sel); else openScene(sel.b, sel.task); return; }
    closeInline();
    // one clip with a poster in the card: play it right there, in the poster's frame
    var poster = pairs.length === 1 ? li.querySelector(".st-poster") : null;
    if (poster) {
      var one = pairs[0], pv = el("video", { playsinline: "", controls: "", loop: "", preload: "auto", src: one.t.video, poster: one.t.poster || null, "aria-label": "Rollout of " + sel.task + ", " + one.exp });
      pv.muted = true;
      poster.hidden = true; poster.parentNode.insertBefore(el("div", { class: "media st-inplace" }, [pv]), poster);
      var ppr = pv.play(); if (ppr && ppr.catch) ppr.catch(function () {});
      if (tourAt >= 0) scrollToEl(li);
      return;
    }
    var vids = [];
    var slots = pairs.map(function (p) {
      var v = el("video", { playsinline: "", controls: "", preload: "auto", src: p.t.video, poster: p.t.poster || null, "aria-label": (p.role || "Rollout") + ": " + sel.task + ", " + p.exp });
      v.muted = true; vids.push(v);
      var ri = RI.get(p.exp), sc = cellVal(p.t);
      return el("figure", { class: "sp-slot" }, [v, el("figcaption", null, [p.role ? el("span", { class: "cvlab", text: p.role }) : null,
        sel.roles ? null : el("b", { text: ri && ri.armLabel && p.role ? ri.armLabel : sel.task }), sc !== null ? el("span", { class: "sc", title: passesText(p.t), text: fmt(sc) + " / 5" }) : null,
        el("code", { class: "rawid", text: p.exp })])]);
    });
    // start together once every clip can play; when all have ended, start again
    var ready = 0, started = false, closed = false;
    function startAll() { if (started || closed) return; started = true; vids.forEach(function (v) { try { v.currentTime = 0; } catch (e) { /* not seekable yet */ } var pr = v.play(); if (pr && pr.catch) pr.catch(function () {}); }); }
    vids.forEach(function (v) {
      v.addEventListener("canplay", function once() { v.removeEventListener("canplay", once); if (++ready >= vids.length) startAll(); });
      v.addEventListener("ended", function () { if (!closed && vids.every(function (x) { return x.ended; })) { started = false; startAll(); } });
    });
    var startTimer = setTimeout(startAll, 4000);
    inlineStop = function () { closed = true; clearTimeout(startTimer); };
    var close = el("button", { type: "button", class: "linkbtn", text: "Close" }); close.addEventListener("click", closeInline);
    var fs = el("button", { type: "button", class: "linkbtn", title: "Full screen (F)", text: "Full screen" });
    var bar = el("p", { class: "sp-bar" }, [el("b", { text: sel.task }), fs, close]);
    if (sel.c) { var full = el("button", { type: "button", class: "linkbtn", text: "Frame by frame" }); full.addEventListener("click", function () { closeInline(); watch(sel); }); bar.insertBefore(full, fs); }
    var box = el("div", { class: "st-play" + (pairs.length === 1 ? " one" : "") }, [bar, el("div", { class: "sp-grid" }, slots)]);
    fs.addEventListener("click", function () { toggleFull(box); });
    box.addEventListener("fullscreenchange", function () { fs.textContent = document.fullscreenElement === box ? "Exit full screen" : "Full screen"; });
    li.appendChild(box);
    // in the tour the clips take the screen; on a click they only scroll into view if they are off it
    if (tourAt >= 0) scrollToEl(box); else if (box.scrollIntoView) box.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  // the judge's individual passes on a 1 to 5 line, with a tick at their mean: the spread behind each number
  function passStrip(t) {
    var ps = (t && t.pass_scores || []).filter(function (x) { return typeof x === "number"; }); if (ps.length < 2) return null;
    var W = 46, H = 12, x = function (v) { return 3 + (Math.max(1, Math.min(5, v)) - 1) / 4 * (W - 6); };
    var svg = sv("svg", { class: "pstrip", viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": "Passes " + ps.map(function (v) { return fmt(v, 1); }).join(", ") });
    svg.appendChild(sv("title", { text: "Judge passes: " + ps.map(function (v) { return String(Math.round(v * 100) / 100); }).join(", ") }));
    svg.appendChild(sv("line", { x1: 3, x2: W - 3, y1: H / 2, y2: H / 2, stroke: "var(--axis)" }));
    ps.forEach(function (v) { svg.appendChild(sv("circle", { cx: x(v), cy: H / 2, r: 2.3, fill: "currentColor", opacity: 0.55 })); });
    svg.appendChild(sv("line", { x1: x(t.mean), x2: x(t.mean), y1: 1, y2: H - 1, stroke: "currentColor", "stroke-width": 1.5 }));
    return svg;
  }
  function numCell(t, cls) {
    var v = cellVal(t), td = el("td", { class: "num" + (cls ? " " + cls : "") });
    if (v === null) { td.appendChild(el("span", { class: "dash", title: t ? "No judged clip for this task in this run" : null, text: t ? "no clip" : "-" })); return td; }
    var strip = passStrip(t); if (strip) td.appendChild(strip);
    td.appendChild(document.createTextNode(fmt(v)));
    if (gateFail(t)) td.appendChild(el("span", { class: "gf", title: "Failed a gate in at least one judge pass", text: "✕" }));
    return td;
  }
  // per-task table: control against each arm; a cell that moved by a full point is marked, and each arm cell opens its clips
  function abEvidence(s) {
    var ctl = tasksOfRun(s.ctl), arms = s.arms.map(function (a) { return tasksOfRun(a[1]); });
    if (!ctl || arms.every(function (a) { return !a; })) return null;
    var ids = Object.keys(ctl).filter(function (k) { return cellVal(ctl[k]) !== null || arms.some(function (a) { return a && cellVal(a[k]) !== null; }); }).sort();
    if (!ids.length) return null;
    var tally = s.arms.map(function () { return { up: 0, down: 0, n: 0 }; }), anyGate = false;
    var hr = el("tr", null, [el("th", { scope: "col", text: "Task" }), el("th", { class: "num", scope: "col", text: "control" })]);
    s.arms.forEach(function (a) { hr.appendChild(el("th", { class: "num", scope: "col", title: a[2] || a[0], text: a[0] })); });
    var tb = el("tbody");
    ids.forEach(function (k) {
      var c = cellVal(ctl[k]), tr = el("tr", null, [el("th", { scope: "row", text: k }), numCell(ctl[k])]);
      if (gateFail(ctl[k])) anyGate = true;
      s.arms.forEach(function (a, i) {
        var t = arms[i] && arms[i][k], v = cellVal(t), d = c !== null && v !== null ? v - c : null;
        if (d !== null) { tally[i].n++; if (d >= MOVE) tally[i].up++; else if (d <= -MOVE) tally[i].down++; }
        if (gateFail(t)) anyGate = true;
        var td = numCell(t, d !== null && d >= MOVE ? "up" : d !== null && d <= -MOVE ? "down" : "");
        if (v !== null && t.video && ctl[k] && ctl[k].video) {
          var b = el("button", { type: "button", class: "cellbtn", "aria-label": "Watch " + k + ": control " + (c === null ? "no score" : fmt(c)) + " against " + (a[2] || a[0]) + " " + fmt(v),
            title: "Watch " + k + ": control against " + (a[2] || a[0]) });
          while (td.firstChild) b.appendChild(td.firstChild);
          if (d !== null && Math.abs(d) >= MOVE) b.appendChild(el("span", { class: "mv", "aria-hidden": "true", text: d > 0 ? "▲" : "▼" }));
          b.addEventListener("click", function () { playIn(s.id, { task: k, b: s.ctl, c: a[1] }); });
          td.appendChild(b);
        }
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    var sum = el("ul", { class: "tally" });
    s.arms.forEach(function (a, i) {
      var t = tally[i]; if (!t.n) { sum.appendChild(el("li", null, [el("b", { text: a[2] || a[0] }), document.createTextNode(": not scored yet")])); return; }
      sum.appendChild(el("li", null, [el("b", { text: a[2] || a[0] }), document.createTextNode(": "),
        el("span", { class: t.up ? "good" : "", text: t.up + " up" }), document.createTextNode(", "),
        el("span", { class: t.down ? "bad" : "", text: t.down + " down" }), document.createTextNode(" of " + t.n + " task" + (t.n === 1 ? "" : "s"))]));
    });
    return { table: el("table", { class: "ev" }, [el("thead", null, [hr]), tb]), sum: sum, gate: anyGate,
      cap: (s.cap || "Judge's mean per task. ▲ ▼ a full point against control. Click a number to play that pair here.") + " Dots are the judge's passes on a 1 to 5 line." };
  }
  // the same settings run several times: tasks at least two runs judged, and the spread between them
  function repeatEvidence(s) {
    var maps = s.runs.map(function (r) { return tasksOfRun(r[1]); });
    if (maps.filter(Boolean).length < 2) return null;
    var seen = {}; maps.forEach(function (m) { if (m) Object.keys(m).forEach(function (k) { if (cellVal(m[k]) !== null) seen[k] = (seen[k] || 0) + 1; }); });
    var ids = Object.keys(seen).filter(function (k) { return seen[k] >= 2; }).sort();
    if (!ids.length) return null;
    var hr = el("tr", null, [el("th", { scope: "col", text: "Task" })]);
    s.runs.forEach(function (r) { hr.appendChild(el("th", { class: "num", scope: "col", title: r[1], text: r[0] })); });
    hr.appendChild(el("th", { class: "num", scope: "col", text: "spread" }));
    var tb = el("tbody"), worst = null, over = 0, anyGate = false;
    ids.forEach(function (k) {
      var vals = maps.map(function (m) { return m ? cellVal(m[k]) : null; }), got = vals.filter(function (v) { return v !== null; });
      var sp = Math.max.apply(null, got) - Math.min.apply(null, got);
      if (!worst || sp > worst.sp) worst = { k: k, sp: sp };
      if (sp >= 0.5) over++;
      var tr = el("tr", null, [el("th", { scope: "row", text: k })]);
      maps.forEach(function (m) { if (gateFail(m && m[k])) anyGate = true; tr.appendChild(numCell(m && m[k])); });
      tr.appendChild(el("td", { class: "num" + (sp >= MOVE ? " down" : ""), text: fmt(sp) }));
      tb.appendChild(tr);
    });
    var sum = el("ul", { class: "tally" }, [el("li", null, [document.createTextNode("Largest spread "), el("b", { text: fmt(worst.sp) }),
      document.createTextNode(" on " + worst.k + ". " + over + " of " + ids.length + " tasks differ by 0.5 or more.")])]);
    return { table: el("table", { class: "ev" }, [el("thead", null, [hr]), tb]), sum: sum, gate: anyGate,
      cap: (s.cap || "Judge's mean per task. Identical settings in every column.") + " Dots are the judge's passes on a 1 to 5 line." };
  }
  function storyState(s) {
    if (s.kind === "note" || s.kind === "gallery") return "ok";
    var exps = s.kind === "repeat" ? s.runs.map(function (r) { return r[1]; }) : [s.ctl].concat(s.arms.map(function (a) { return a[1]; }));
    if (s.kind === "repeat" ? exps.filter(tasksOfRun).length >= 2 : tasksOfRun(s.ctl) && s.arms.some(function (a) { return tasksOfRun(a[1]); })) return "ok";
    var rows = exps.map(rowByExp).filter(Boolean);
    if (rows.some(function (r) { return r.overall !== null; })) return "loading";
    if (rows.some(function (r) { return r.status === "running" && !isStale(r); })) return "running";
    if (rows.some(function (r) { return r.status === "generated"; })) return "generated";
    return rows.length ? "ended" : "none";
  }
  // the full record behind a finding, built when it is opened: every run with its flags, commit and job, then per task
  // every run's mean, passes, gate status and the judge's comment. ?finding=ID opens it.
  function findingDetail(s, exps) {
    var labels = {};
    if (s.kind === "repeat") s.runs.forEach(function (r) { labels[r[1]] = r[0]; });
    else { labels[s.ctl] = "control"; s.arms.forEach(function (a) { labels[a[1]] = a[2] || a[0]; }); }
    var body = el("div", { class: "more-body" }), built = false;
    var d = el("details", { class: "st-more", id: "detail-" + s.id }, [el("summary", { text: "Every score, judge comment and run" }), body]);
    d.addEventListener("toggle", function () {
      if (!d.open || built) return; built = true;
      var hr = el("tr", null, ["Run", "Flags", "Commit", "Job", "Passes"].map(function (h) { return el("th", { scope: "col", text: h }); }));
      var tb = el("tbody");
      exps.forEach(function (e) {
        var r = rowByExp(e), ri = RI.get(e), m = MANS[e]; if (!m) return;
        var sha = (m.git_sha || (r && r.sha) || "");
        tb.appendChild(el("tr", null, [
          el("th", { scope: "row" }, [document.createTextNode(labels[e] || e), el("code", { class: "rawid", text: e })]),
          el("td", { class: "wrapcell", text: ri && ri.words ? (ri.words.length ? ri.words.join(", ") : "no flags") : "not recorded" }),
          el("td", null, [/^[0-9a-f]{7,40}$/i.test(sha) ? el("a", { href: COMMIT + sha, target: "_blank", rel: "noopener", text: sha.slice(0, 7) }) : el("span", { class: "dash", text: "-" })]),
          el("td", null, [r && /^https:\/\/github\.com\//.test(r.run_url || "") ? el("a", { href: r.run_url, target: "_blank", rel: "noopener", text: "job" }) : el("span", { class: "dash", text: "-" })]),
          el("td", { class: "num", text: r && r.passes !== null ? String(r.passes) : "-" })]));
      });
      body.appendChild(el("div", { class: "xscroll" }, [el("table", { class: "ev runs-ev" }, [el("thead", null, [hr]), tb])]));
      var ids = {}; exps.forEach(function (e) { var tm = tasksOfRun(e); if (tm) Object.keys(tm).forEach(function (k) { ids[k] = 1; }); });
      Object.keys(ids).sort().forEach(function (k) {
        var blk = el("div", { class: "task-blk" }, [el("h4", { text: k })]);
        exps.forEach(function (e) {
          var t = (tasksOfRun(e) || {})[k]; if (!t) return;
          var v = cellVal(t), st = (t.status || []).join(", ");
          var head = el("p", { class: "task-run" }, [el("b", { text: labels[e] || e }), el("span", { class: "sc", text: v === null ? "no clip" : fmt(v) }),
            el("span", { class: "std", text: (passesText(t) || "") + (st ? (passesText(t) ? " · " : "") + st : "") })]);
          blk.appendChild(head);
          var jc = judgeComment(t, true); if (jc) blk.appendChild(jc);
        });
        body.appendChild(blk);
      });
    });
    return d;
  }
  function openFinding(id) {
    var d = $("detail-" + id), li = $("story-" + id); if (!li) return;
    if (d) d.open = true;
    scrollToEl(li);
  }
  var storyShown = [];
  function renderStory() {
    var ol = $("story-list"); if (!ol) return; clear(ol); storyShown = [];
    STORY.forEach(function (s) {
      var st = storyState(s);
      // a finding whose runs ended without a score is not a finding; one still running is shown as pending
      if (st === "ended" || st === "none" || (st === "generated" && !s.pending)) return;
      if (s.kind === "gallery") {
        // the examples by task type are the first finding: renderGallery() fills #gal
        var gli = el("li", { class: "st solo", id: "story-" + s.id }, [el("h3", { text: (storyShown.length + 1) + ". " + s.title }),
          el("div", { class: "gal", id: "gal" }), el("p", { class: "st-cap", id: "gal-note" })]);
        ol.appendChild(gli); storyShown.push({ s: s, li: gli, ev: false }); return;
      }
      var moreFor = null;
      var ev = st !== "ok" ? null : s.kind === "repeat" ? repeatEvidence(s) : s.kind === "note" ? null : abEvidence(s);
      var n = storyShown.length + 1;
      var text = el("div", { class: "st-text" }, [
        el("h3", { text: n + ". " + s.title }), s.body ? el("p", { class: "st-body", text: s.body }) : null]);
      if (s.points) text.appendChild(el("ul", { class: "st-points" }, s.points.map(function (t) { return el("li", { text: t }); })));
      var acts = el("p", { class: "st-acts" });
      if (s.watch && ev) {
        var wb = el("button", { type: "button", class: "cvbtn primary", text: s.watchLabel || "Watch " + s.watch.task });
        wb.addEventListener("click", function () { playIn(s.id, watchSel(s)); }); acts.appendChild(wb);
      }
      if (s.scene && MANS[s.scene[0]]) {
        var sb = el("button", { type: "button", class: "cvbtn primary", text: s.sceneLabel || "Watch " + s.scene[1] });
        sb.addEventListener("click", function () { playIn(s.id, { task: s.scene[1], b: s.scene[0] }); }); acts.appendChild(sb);
      }
      (s.links || []).forEach(function (l) { acts.appendChild(el("a", { href: l[1], target: "_blank", rel: "noopener", text: l[0] })); });
      if (acts.firstChild) text.appendChild(acts);
      var side = el("div", { class: "st-ev" });
      if (ev) {
        side.appendChild(ev.table); side.appendChild(ev.sum);
        side.appendChild(el("p", { class: "st-cap", text: ev.cap + (ev.gate ? " ✕ gate failed in a pass." : "") }));
        var bd = el("div", { class: "badges" });
        var exps = s.kind === "repeat" ? s.runs.map(function (r) { return r[1]; }) : [s.ctl].concat(s.arms.map(function (a) { return a[1]; }));
        var rows = exps.map(rowByExp).filter(Boolean);
        if (rows.some(isOpen)) bd.appendChild(el("span", { class: "badge warn", title: "Fixed action scripts from the dataset, no AI player. Used for A/B tests only, never for final scores.", text: "open loop, A/B only" }));
        if (s.kind !== "repeat") bd.appendChild(s.seeds === 2 ? badge("", "two seeds", "Control and treatment were each generated on two seeds. This table shows one of them.")
          : badge("warn", "one seed", "One generation per arm. The adoption rule asks for the gain to repeat on a second seed."));
        var ps = rows.map(function (r) { return r.passes; }).filter(function (p) { return p !== null; });
        if (ps.length) bd.appendChild(el("span", { class: "badge", text: Math.min.apply(null, ps) + " judge passes" }));
        side.appendChild(bd);
        // where each number comes from: the pull request that proposed the change and the Actions job of every run
        var prov = el("p", { class: "st-prov" });
        (s.prs || []).forEach(function (n) { prov.appendChild(el("a", { href: PR + n, target: "_blank", rel: "noopener", text: "PR #" + n })); });
        rows.forEach(function (r) {
          if (r.run_url && /^https:\/\/github\.com\//.test(r.run_url)) prov.appendChild(el("a", { href: r.run_url, target: "_blank", rel: "noopener", title: "GitHub Actions job that generated and scored " + r.exp, text: r.exp + " job" }));
        });
        if (prov.firstChild) side.appendChild(prov);
        moreFor = findingDetail(s, exps);
      } else if (s.kind !== "note") {
        side.appendChild(el("p", { class: "st-pend" }, [el("span", { class: "badge " + (st === "running" ? "warn" : ""), text: st === "running" ? "running now" : st === "generated" ? "generated, not scored yet" : "loading scores" }),
          document.createTextNode(" Scores appear here when the judge has scored every arm.")]));
      } else if (s.scene) {
        var t0 = MANS[s.scene[0]] && (MANS[s.scene[0]].tasks || []).filter(function (t) { return t.task_id === s.scene[1]; })[0];
        if (t0 && t0.poster) {
          var pb = el("button", { type: "button", class: "st-poster", "aria-label": s.sceneLabel || "Watch " + s.scene[1] }, [el("img", { src: t0.poster, alt: "", loading: "lazy" })]);
          pb.addEventListener("click", function () { playIn(s.id, { task: s.scene[1], b: s.scene[0] }); });
          side.appendChild(pb);
        }
      }
      var li = el("li", { class: "st" + (ev || s.kind === "note" ? "" : " pend") + (side.firstChild ? "" : " solo"), id: "story-" + s.id }, side.firstChild ? [text, side] : [text]);
      if (moreFor) li.appendChild(moreFor);
      ol.appendChild(li); storyShown.push({ s: s, li: li, ev: !!ev });
    });
    if (!storyShown.length) ol.appendChild(el("li", { class: "empty", text: "No findings to show yet." }));
    renderGallery(); renderVerdicts(); buildTour();
  }

  /* ---------- verdict table: every A/B in the findings on one screen ---------- */
  function abTally(s) {
    var ctl = tasksOfRun(s.ctl); if (!ctl) return null;
    var n = 0, up = 0, down = 0, tasks = {};
    s.arms.forEach(function (a) {
      var m = tasksOfRun(a[1]); if (!m) return;
      Object.keys(ctl).forEach(function (k) {
        var c = cellVal(ctl[k]), v = cellVal(m[k]); if (c === null || v === null) return;
        n++; tasks[k] = 1; if (v - c >= MOVE) up++; else if (v - c <= -MOVE) down++;
      });
    });
    return n ? { n: n, up: up, down: down, tasks: Object.keys(tasks).length, arms: s.arms.filter(function (a) { return tasksOfRun(a[1]); }).length } : null;
  }
  function noiseFloor() {
    var s = STORY.filter(function (x) { return x.id === "noise"; })[0]; if (!s) return null;
    var maps = s.runs.map(function (r) { return tasksOfRun(r[1]); }).filter(Boolean); if (maps.length < 2) return null;
    var worst = 0, seen = {};
    maps.forEach(function (m) { Object.keys(m).forEach(function (k) { seen[k] = 1; }); });
    Object.keys(seen).forEach(function (k) {
      var got = maps.map(function (m) { return cellVal(m[k]); }).filter(function (v) { return v !== null; });
      if (got.length >= 2) worst = Math.max(worst, Math.max.apply(null, got) - Math.min.apply(null, got));
    });
    return worst;
  }
  function renderVerdicts() {
    var box = $("verdicts"); if (!box) return; clear(box);
    var rows = STORY.filter(function (s) { return s.verdict && storyShown.some(function (x) { return x.s === s; }); });
    if (!rows.length) { box.hidden = true; return; }
    box.hidden = false;
    var nf = noiseFloor();
    box.appendChild(el("p", { class: "vd-rule" }, [el("b", { text: "The bar. " }),
      document.createTextNode("A task moves only at 1.0 on the mean of its judge passes (2 to 4). Adoption needs the gain on two seeds, with the AI player, and no gate broken." +
        (nf !== null ? " Measured noise between identical runs: up to " + fmt(nf) + "." : ""))]));
    var hr = el("tr", null, [el("th", { scope: "col", text: "Change" }), el("th", { class: "num", scope: "col", text: "Arms" }), el("th", { class: "num", scope: "col", text: "Tasks" }),
      el("th", { class: "num", scope: "col", text: "Up" }), el("th", { class: "num", scope: "col", text: "Down" }), el("th", { scope: "col", text: "Verdict" })]);
    var tb = el("tbody");
    rows.forEach(function (s) {
      var t = s.kind === "repeat" ? null : abTally(s);
      var a = el("a", { href: "#story-" + s.id, text: s.label || s.title });
      var tr = el("tr", null, [el("th", { scope: "row" }, [a])]);
      [t ? t.arms : null, t ? t.tasks : null].forEach(function (v) { var td = el("td", { class: "num" }); if (v === null) dashCell(td); else td.textContent = String(v); tr.appendChild(td); });
      [["up", "good"], ["down", "bad"]].forEach(function (k) {
        var td = el("td", { class: "num" }); if (!t) dashCell(td); else td.appendChild(el("span", { class: t[k[0]] ? k[1] : "", text: String(t[k[0]]) }));
        tr.appendChild(td);
      });
      var cls = /dropped/.test(s.verdict) ? "bad" : /running/.test(s.verdict) ? "warn" : "";
      tr.appendChild(el("td", null, [el("span", { class: "badge " + cls, text: s.verdict })]));
      tb.appendChild(tr);
    });
    box.appendChild(el("table", { class: "ev vd" }, [el("thead", null, [hr]), tb]));
    box.appendChild(el("p", { class: "st-cap", text: "Up and down count task-by-arm cells that moved a full point against control. Fixed moves; one seed unless the row says two." }));
  }

  /* ---------- hero: verdict line and the project in numbers ---------- */
  function renderVerdict() {
    var p = $("verdict"); if (!p) return; clear(p);
    var fin = bestFinal(), shown = fin || bestClosed();
    if (!shown) { p.hidden = true; return; }
    p.hidden = false;
    var beat = fin && fin.overall - TARGET >= 2 * (fin.overall_std || FALLBACK_STD);
    p.appendChild(el("b", { text: fin ? (beat ? "Yes. " : "No. ") : "Not yet. " }));
    p.appendChild(document.createTextNode(fin ? "Final score " + fmt(fin.overall) + " on all " + FULL_TASKS + " tasks. Genie 3: " + fmt(TARGET) + "."
      : "Best official score " + fmt(shown.overall) + " on " + shown.n_tasks + " of " + FULL_TASKS + " tasks. Genie 3: " + fmt(TARGET) + ". " +
        (ADOPTED.length ? "Adopted: " + ADOPTED.join(", ") + "." : "No change adopted.")));
  }
  function renderGlance() {
    var p = $("glance"); if (!p) return; clear(p);
    var real = realRows(), scored = real.filter(function (r) { return r.overall !== null; });
    var groups = {}; real.forEach(function (r) { var m = /\[arm \d+\/\d+ of ([^:\]]+)/.exec(r.notes || ""); if (m) groups[m[1]] = 1; });
    var judged = 0; scored.forEach(function (r) { judged += (r.n_tasks || 0) * (r.passes || 0); });
    var clipsN = 0; ((scenesIdx && scenesIdx.runs) || []).forEach(function (r) { clipsN += r.n_tasks || 0; });
    var nGroups = Object.keys(groups).length;
    p.textContent = real.length + " runs logged, failed ones included, in " + nGroups + " A/B groups. " + judged + " official task scores" + (clipsN ? ". " + clipsN + " clips published." : ".");
  }


  /* ---------- gallery: per family, the highest- and lowest-scored rollout with the judge's comment ---------- */
  // pool: officially scored, uncapped rollouts of the 14B runner that have a clip and a judge comment
  function clipPool() {
    var out = [];
    Object.keys(MANS).forEach(function (exp) {
      var m = MANS[exp], row = rowByExp(exp);
      if (!m || m.scored === false || m.runner !== "lingbot_world2" || (row && isCapped(row)) || m.max_chunks) return;
      (m.tasks || []).forEach(function (t) {
        if (cellVal(t) === null || !t.video || !/^https:/.test(t.video) || !(t.reason_en || t.reason)) return;
        out.push({ t: t, man: m, exp: exp, row: row, mean: t.mean, gen: m.generated || "" });
      });
    });
    return out;
  }
  function pickBest(list) {
    return list.slice().sort(function (a, b) { return b.mean - a.mean || (a.gen < b.gen ? 1 : -1); })[0] || null;
  }
  // lowest mean; among ties the longest comment, which says most about what went wrong; never the same task as the best
  function pickWorst(list, best) {
    var l = list.filter(function (c) { return !best || c.t.task_id !== best.t.task_id; });
    return l.sort(function (a, b) { return a.mean - b.mean || (b.t.reason_en || b.t.reason).length - (a.t.reason_en || a.t.reason).length; })[0] || null;
  }
  function driverBadge(row) {
    if (!row) return null;
    if (isOpen(row)) return el("span", { class: "badge warn", title: "Fixed action scripts from the dataset, no AI player. A/B only, never a final score.", text: "open loop" });
    if (isScripted(row)) return el("span", { class: "badge warn", title: "Dataset moves replayed chunk by chunk, no AI player.", text: "scripted moves" });
    return el("span", { class: "badge ok", text: "AI played" });
  }
  function clipCard(c, role) {
    var t = c.t, media = el("div", { class: "media" });
    media.appendChild(el("img", { src: t.poster || "", alt: "First frame of " + t.task_id, loading: "lazy" }));
    var pb = el("button", { class: "play", type: "button", "aria-label": "Play " + t.task_id + ", " + role });
    pb.addEventListener("click", function () {
      var v = el("video", { controls: "", playsinline: "", loop: "", src: t.video, poster: t.poster || null, "aria-label": "Rollout of " + t.task_id });
      v.muted = true; clear(media); media.appendChild(v);
      var pr = v.play(); if (pr && pr.catch) pr.catch(function () {});
      v.focus();
    });
    media.appendChild(pb);
    var np = (t.pass_scores || []).length;
    var head = el("div", { class: "gc-head" }, [el("span", { class: "cvlab " + (role === "highest" ? "good" : "bad"), text: role === "highest" ? "Highest" : "Lowest" }),
      el("b", { text: t.task_id }), el("span", { class: "sc", title: passesText(t), text: fmt(t.mean) + " / 5" })]);
    var quote = el("blockquote", { class: "gc-q", text: t.reason_en || t.reason });
    // the judge's own text is authoritative: a translated quote always carries it behind "show original"
    var orig = null, tog = null;
    if (t.reason_en) {
      orig = el("p", { class: "jorig", text: t.reason }); orig.hidden = true;
      tog = el("button", { type: "button", class: "jtoggle", "aria-expanded": "false", text: "show original" });
      tog.addEventListener("click", function () {
        orig.hidden = !orig.hidden; tog.textContent = orig.hidden ? "show original" : "hide original";
        tog.setAttribute("aria-expanded", String(!orig.hidden));
      });
    }
    var foot = el("div", { class: "badges" }, [driverBadge(c.row), np ? el("span", { class: "badge", text: np + " judge passes" }) : null,
      (t.status || []).indexOf("gate_fail") >= 0 ? el("span", { class: "badge bad", title: "Failed a gate in at least one judge pass", text: "gate failed" }) : null]);
    var link = el("a", { class: "sclink", href: sceneLink(c.exp, t.task_id), text: "Open in Scenes" });
    link.addEventListener("click", function (e) { e.preventDefault(); openScene(c.exp, t.task_id); });
    return el("article", { class: "scene gc" }, [head, media, quote, tog, orig, foot,
      el("div", { class: "row" }, [el("code", { class: "rawid", text: c.exp }), link])]);
  }
  var galFam = "gc";
  function renderGallery(focus) {
    var box = $("gal"); if (!box) return;
    var pool = clipPool(); if (!pool.length) { if (scenesIdx) { clear(box); renderHeroClip(pool); box.appendChild(el("p", { class: "note", text: "No officially scored clips published yet." })); } return; }
    clear(box);
    var b = bestFinal() || bestClosed(), lb = REFS.filter(function (r) { return r.exp === "LingBot-World2"; })[0];
    var tabs = segmented("Task type", FAMS.map(function (f) { return [f[0], FAMINFO[f[0]].name]; }), galFam, function (k, viaKey) { galFam = k; renderGallery(viaKey); });
    box.appendChild(tabs);
    if (focus) { var cur = tabs.querySelector('[aria-selected="true"]'); if (cur) cur.focus(); }
    var k = galFam, info = FAMINFO[k], list = pool.filter(function (c) { return c.t.family === k; });
    var best = pickBest(list), worst = pickWorst(list, best);
    var scores = el("dl", { class: "kv" }, [el("dt", { text: "Genie 3" }), el("dd", { text: fmt(GENIE[k]) }), el("dt", { text: "LingBot v2" }), el("dd", { text: fmt(lb[k]) }),
      b && b[k] !== null ? el("dt", { text: "Ours, " + b.n_tasks + " tasks" }) : null, b && b[k] !== null ? el("dd", { text: fmt(b[k]) }) : null]);
    var head = el("div", { class: "gf-head" }, [el("p", { class: "gf-q", text: info.ask }), scores]);
    var cards = el("div", { class: "gf-cards" });
    if (best) cards.appendChild(clipCard(best, "highest"));
    if (worst) cards.appendChild(clipCard(worst, "lowest"));
    if (!best) cards.appendChild(el("p", { class: "note", text: "No scored rollout for this task type yet." }));
    box.appendChild(el("div", { class: "gfam", id: "gallery-" + k, role: "tabpanel" }, [head, cards]));
    $("gal-note").textContent = "Quotes are the official judge's comments, machine-translated. Chosen from " + pool.length + " scored 14B rollouts by pass mean; ties on the lowest go to the longest comment. Most use fixed moves.";
    renderHeroClip(pool);
  }
  // header: the highest-scored rollout so far, looping muted; labelled as one rollout, never as the score
  function renderHeroClip(pool) {
    var fig = $("heroclip"); if (!fig) return;
    var c = pickBest(pool); if (!c) { fig.hidden = true; return; }
    if (fig.getAttribute("data-clip") === c.exp + "/" + c.t.task_id) return;
    clear(fig); fig.hidden = false; fig.setAttribute("data-clip", c.exp + "/" + c.t.task_id);
    var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var v = el("video", { playsinline: "", loop: "", preload: calm ? "none" : "auto", poster: c.t.poster || null, src: c.t.video, "aria-label": "Rollout of " + c.t.task_id });
    v.muted = true; if (calm) v.setAttribute("controls", ""); else { v.autoplay = true; var pr = v.play(); if (pr && pr.catch) pr.catch(function () { v.setAttribute("controls", ""); }); }
    v.title = "Click for full screen"; v.addEventListener("click", function () { toggleFull(v); });
    fig.appendChild(v);
    var cap = el("figcaption", null, [el("b", { text: c.t.task_id + ", scored " + fmt(c.mean) + " of 5." }),
      document.createTextNode(" Our highest-scored rollout" + (c.row && !isClosed(c.row) ? ", fixed moves" : "") + ". ")]);
    var a = el("a", { href: "#story-examples", text: "What breaks" }); cap.appendChild(a);
    fig.appendChild(cap);
  }

  /* ---------- timeline: every logged run by its CSV timestamp. That is the last write of the row: report time for a scored run,
     end time for a generated, failed or cancelled one, launch time only while it is still running. ---------- */
  function renderTimeline() {
    var card = $("tl"), host = $("tl-chart"); if (!card || !host) return;
    var rows = realRows().filter(function (r) { return r.t !== null; }).sort(function (a, b) { return a.t - b.t; });
    if (rows.length < 3) { card.hidden = true; return; }
    card.hidden = false; clear(host);
    var W = Math.max(300, host.clientWidth || 900), R = W < 520 ? 3 : 4, step = R * 2 + 2, m = { l: 8, r: 8 };
    var t0 = rows[0].t, t1 = rows[rows.length - 1].t, span = Math.max(1, t1 - t0);
    var cols = Math.max(8, Math.floor((W - m.l - m.r) / step)), stacks = {}, maxStack = 0;
    var pts = rows.map(function (r) {
      var c = Math.min(cols - 1, Math.floor((r.t - t0) / span * (cols - 1) + 0.5)), k = stacks[c] = (stacks[c] || 0) + 1;
      if (k > maxStack) maxStack = k;
      return { r: r, c: c, k: k };
    });
    // merged pull requests in the same window, stacked downward under the axis (from the GitHub API, when it answered)
    var prStacks = {}, maxPr = 0, S = R * 2 - 1;
    var prPts = (MERGED || []).filter(function (q) { return q.t >= t0 && q.t <= t1; }).sort(function (a, b) { return a.t - b.t; }).map(function (q) {
      var c = Math.min(cols - 1, Math.floor((q.t - t0) / span * (cols - 1) + 0.5)), k = prStacks[c] = (prStacks[c] || 0) + 1;
      if (k > maxPr) maxPr = k;
      return { q: q, c: c, k: k };
    });
    var top = 8, base = top + maxStack * step, below = maxPr ? 8 + maxPr * step : 0, H = base + below + 26;
    var x = function (c) { return m.l + R + c * ((W - m.l - m.r - 2 * R) / (cols - 1)); };
    var svg = sv("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": rows.length + " runs by the time their row was last written" });
    svg.appendChild(sv("line", { x1: m.l, x2: W - m.r, y1: base + 4, y2: base + 4, stroke: "var(--axis)" }));
    var hour = 3600000, first = Math.ceil(t0 / hour) * hour, every = span / hour > 12 ? 3 : span / hour > 6 ? 2 : 1;
    for (var h = first; h <= t1; h += hour * every) {
      var hx = m.l + R + (h - t0) / span * (W - m.l - m.r - 2 * R);
      svg.appendChild(sv("line", { x1: hx, x2: hx, y1: base + 4, y2: base + 8, stroke: "var(--axis)" }));
      svg.appendChild(sv("text", { x: hx, y: base + below + 21, "text-anchor": "middle", text: pad2(new Date(h).getUTCHours()) + ":00" }));
    }
    var n = { scored: 0, generated: 0, running: 0, ended: 0 };
    pts.forEach(function (p) {
      var r = p.r, kind = r.overall !== null ? "scored" : isEnded(r) ? "ended" : r.status === "running" ? "running" : "generated";
      n[kind]++;
      var col = kind === "scored" ? "var(--s1)" : kind === "ended" ? "var(--bad)" : kind === "running" ? "var(--warn)" : "var(--ref)";
      var dot = sv("circle", { cx: x(p.c), cy: base - (p.k - 1) * step - R, r: R, fill: kind === "scored" ? col : "var(--surface)", stroke: col, "stroke-width": 1.5 });
      dot.appendChild(sv("title", { text: r.exp + " · " + fmtTime(r.t) + " UTC · " + (kind === "scored" ? "scored " + fmt(r.overall) + " on " + r.n_tasks + " tasks" : kind === "ended" ? (isStale(r) ? "no result" : r.status) : kind) }));
      if (r.run_url && /^https:\/\/github\.com\//.test(r.run_url)) { var ln = sv("a", { href: r.run_url, target: "_blank", rel: "noopener" }); ln.appendChild(dot); svg.appendChild(ln); }
      else svg.appendChild(dot);
    });
    prPts.forEach(function (p) {
      var q = p.q, sq = sv("rect", { x: x(p.c) - S / 2, y: base + 10 + (p.k - 1) * step, width: S, height: S, rx: 1.5, fill: "var(--ink)" });
      sq.appendChild(sv("title", { text: "PR #" + q.number + " merged " + fmtTime(q.t) + " UTC · " + q.title }));
      var ln = sv("a", { href: q.url, target: "_blank", rel: "noopener" }); ln.appendChild(sq); svg.appendChild(ln);
    });
    host.appendChild(svg);
    var hrs = span / hour, cap = $("tl-cap"); clear(cap);
    function key(col, fill, text) { return el("span", { class: "tl-key" }, [el("i", { style: "border-color:" + col + ";background:" + (fill ? col : "transparent") }), document.createTextNode(text)]); }
    cap.appendChild(document.createTextNode(rows.length + " runs in " + (hrs >= 10 ? Math.round(hrs) : hrs.toFixed(1)) + " hours (UTC). A scored run sits at its report time, a failed one at its end, a running one at its launch. Each mark opens its job or pull request. "));
    cap.appendChild(key("var(--s1)", true, n.scored + " scored"));
    cap.appendChild(key("var(--ref)", false, n.generated + " not scored"));
    if (n.running) cap.appendChild(key("var(--warn)", false, n.running + " running"));
    cap.appendChild(key("var(--bad)", false, n.ended + " failed or cancelled"));
    if (prPts.length) cap.appendChild(el("span", { class: "tl-key" }, [el("i", { class: "sq" }), document.createTextNode(prPts.length + " pull requests merged in the same hours, below the line")]));
  }

  /* ---------- how a test runs ---------- */
  var GH = "https://github.com/" + REPO + "/";
  var LOOP = [
    ["Propose", "A pull request adds one change as a runner flag, off by default, with a counter in the log.", "pull requests", GH + "pulls?q=is%3Apr"],
    ["Run", "A GitHub Actions workflow runs every arm on the same tasks and seed on Modal H100s.", "arms workflow", GH + "actions/workflows/arms.yml"],
    ["Judge", "The same job scores each clip with PlayWorld's verifier, Gemini 3.1 Pro, two to four passes.", "experiment workflow", GH + "actions/workflows/experiment.yml"],
    ["Decide", "A task moves at a full point. Adoption needs it on two seeds with no gate broken.", "plan of record", BLOB + "AGENTS.md#plan-of-record"],
    ["Publish", "The job commits the row, the judge's reasons and the clips to main. This page reads them live.", "results/", GH + "tree/main/results"]
  ];
  function renderLoop() {
    var ol = $("loop-steps"); if (!ol) return; clear(ol);
    LOOP.forEach(function (x, i) {
      ol.appendChild(el("li", null, [el("div", { class: "lp-h" }, [el("b", { text: (i + 1) + ". " + x[0] })]),
        el("p", { text: x[1] }), el("a", { href: x[3], target: "_blank", rel: "noopener", text: x[2] })]));
    });
    var note = $("loop-note"); clear(note);
    note.appendChild(document.createTextNode("14B model load: about 207 s down to 31 s, bit-identical weights ("));
    note.appendChild(el("a", { href: PR + "79", target: "_blank", rel: "noopener", text: "PR #79" }));
    note.appendChild(document.createTextNode("). CI does not cover GPU generation, scoring or player calls."));
  }


  /* ---------- the audit trail: proposals are pull requests, experiments are Actions runs (counts from the public GitHub API) ---------- */
  var API = "https://api.github.com/";
  // answers are kept for 10 minutes in sessionStorage, so reloading during a demo does not spend the 60 calls an hour GitHub allows
  function ghJson(path) {
    var key = "pwa-gh:" + path;
    try { var hit = JSON.parse(sessionStorage.getItem(key) || "null"); if (hit && Date.now() - hit.t < 600000) return Promise.resolve(hit.j); } catch (e) { /* storage blocked */ }
    return get(API + path, 8000).then(JSON.parse).then(function (j) {
      try { sessionStorage.setItem(key, JSON.stringify({ t: Date.now(), j: j })); } catch (e) { /* too large or blocked */ }
      return j;
    });
  }
  // one proposal shown in full as the example of the format; merged pull requests with their merge times for the timeline
  var EXAMPLE_PR = 123, MERGED = null;
  function plainBody(md) {
    return String(md || "").replace(/\r/g, "").replace(/<!--[\s\S]*?-->/g, "").replace(/^#{1,6}\s*/gm, "").replace(/\*\*([^*]+)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1")
      .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, "$1").replace(/\n{3,}/g, "\n\n").trim();
  }
  function renderTrail() {
    var box = $("trail"); if (!box) return;
    function stat(n, label, href) { return el("a", { class: "tr-stat", href: href, target: "_blank", rel: "noopener" }, [el("b", { text: n === null ? "-" : String(n) }), el("span", { text: label })]); }
    function draw(d) {
      clear(box);
      var row = el("div", { class: "tr-stats" }, [
        stat(d.merged, "pull requests merged", GH + "pulls?q=is%3Apr+is%3Amerged"),
        stat(d.open ? d.open.length : null, "proposals open", GH + "pulls"),
        stat(d.exp, "experiment workflow runs", GH + "actions/workflows/experiment.yml"),
        stat(d.arms, "arms workflow runs", GH + "actions/workflows/arms.yml")]);
      box.appendChild(row);
      if (d.example) {
        var ex = d.example, body = plainBody(ex.body);
        box.appendChild(el("h3", { text: "One proposal, as written" }));
        box.appendChild(el("article", { class: "tr-pr" }, [
          el("p", { class: "tr-pr-h" }, [el("a", { href: ex.html_url, target: "_blank", rel: "noopener", text: "#" + ex.number }), el("b", { text: " " + ex.title }),
            el("span", { class: "badge " + (ex.merged_at ? "ok" : ""), text: ex.merged_at ? "merged " + fmtTime(Date.parse(ex.merged_at)) + " UTC" : ex.state })]),
          el("div", { class: "tr-pr-b", tabindex: "0", role: "region", "aria-label": "Pull request description", text: body || "No description." })]));
      }
      box.appendChild(el("p", { class: "st-cap", text: d.live ? "Counts from the GitHub API when this page loaded." : "GitHub's API did not answer, so the counts are missing. The links still work." }));
    }
    draw({ merged: null, open: null, exp: null, arms: null, example: null, live: false });
    var d = { merged: null, open: null, exp: null, arms: null, example: null, live: false };
    function part(p, set) { return p.then(function (j) { set(j); d.live = true; }, function () {}); }
    Promise.all([
      part(ghJson("search/issues?q=repo:" + REPO + "+is:pr+is:merged&per_page=1"), function (j) { d.merged = j.total_count; }),
      part(ghJson("repos/" + REPO + "/pulls?state=open&per_page=100"), function (j) { d.open = j.map(function (x) { return { number: x.number, title: x.title, html_url: x.html_url }; }); }),
      part(ghJson("repos/" + REPO + "/actions/workflows/experiment.yml/runs?per_page=1"), function (j) { d.exp = j.total_count; }),
      part(ghJson("repos/" + REPO + "/actions/workflows/arms.yml/runs?per_page=1"), function (j) { d.arms = j.total_count; }),
      part(ghJson("repos/" + REPO + "/pulls/" + EXAMPLE_PR), function (j) { d.example = { number: j.number, title: j.title, body: j.body, html_url: j.html_url, merged_at: j.merged_at, state: j.state }; }),
      part(ghJson("repos/" + REPO + "/pulls?state=closed&sort=updated&direction=desc&per_page=100"), function (j) {
        MERGED = j.filter(function (x) { return x.merged_at; }).map(function (x) { return { number: x.number, title: x.title, url: x.html_url, t: Date.parse(x.merged_at) }; });
      })
    ]).then(function () { draw(d); renderTimeline(); });
  }

  /* ---------- guided tour: a bar that walks the page in order; arrow keys step, Esc exits, ?tour=N deep links ---------- */
  // two lengths: the short tour (about 90 seconds on Auto: question, verdicts, three findings, what is open, method) and the full one
  var tourSteps = [], tourAt = -1, tourFull = false;
  function tourStart(full) { tourFull = !!full; buildTour(); tourGo(0); $("tour-next").focus(); }
  function buildTour() {
    var shown = bestFinal() || bestClosed();
    var steps = [{ el: function () { return $("top"); }, title: "The question", line: "Can we lift an open world model past Genie 3 (" + fmt(TARGET) + ") without retraining it?" }];
    if (tourFull) steps.push({ el: function () { return $("scores"); }, title: "Where we start",
      line: shown ? "Best official score, AI played: " + fmt(shown.overall) + " on " + shown.n_tasks + " tasks (" + shown.exp + "). Genie 3: " + fmt(TARGET) + "." : "No run big enough to estimate a score yet." });
    if ($("verdicts") && !$("verdicts").hidden) steps.push({ el: function () { return $("verdicts"); }, title: "The bar, and the verdicts", line: "A full point, on two seeds, with the AI player. Nothing has cleared it yet." });
    storyShown.forEach(function (x) {
      var s = x.s;
      if (!tourFull && !s.short) return;
      steps.push({ el: function () { return x.li; }, title: s.title, line: s.say || "" });
      if (s.watch && x.ev && (tourFull || s.id !== "window")) steps.push({ el: function () { return x.li; }, run: function () { playIn(s.id, watchSel(s)); }, title: "Watch " + s.watch.task, line: (s.kind === "repeat" ? "" : "Control left, treatment right. ") + (s.say || "") });
      else if (s.scene && MANS[s.scene[0]]) steps.push({ el: function () { return x.li; }, run: function () { playIn(s.id, { task: s.scene[1], b: s.scene[0] }); }, title: "Watch " + s.scene[1], line: s.say || "" });
    });
    steps.push({ el: function () { return $("loop"); }, title: "Method", line: "Proposals are pull requests. GitHub Actions runs, scores and publishes every experiment." });
    if (tourFull) steps.push({ el: function () { return $("watch"); }, run: function () { closeInline(); setMode("tests", false); scrollToEl($("watch")); }, title: "Every change we tested", line: "Each row is an A/B with its runs, including the ones that failed." });
    if (tourFull) steps.push({ el: function () { return $("watch"); }, run: function () { closeInline(); setMode("runs", false); scrollToEl($("watch")); }, title: "Every run", line: "Each row links its commit and job." });
    tourSteps = steps;
    if (tourAt >= 0) tourShow();
  }
  function tourShow() {
    var bar = $("tour"), s = tourSteps[tourAt]; if (!bar || !s) return;
    bar.hidden = false; document.body.classList.add("touring");
    $("tour-n").textContent = (tourAt + 1) + " / " + tourSteps.length;
    $("tour-title").textContent = s.title; $("tour-line").textContent = s.line;
    $("tour-prog").style.width = ((tourAt + 1) / tourSteps.length * 100) + "%";
    $("tour-prev").disabled = tourAt === 0;
    $("tour-next").textContent = tourAt === tourSteps.length - 1 ? "Done" : "Next";
    Array.prototype.forEach.call(document.querySelectorAll(".tour-on"), function (n) { n.classList.remove("tour-on"); });
    var node = s.el(); if (node && node.classList && node.id !== "top") node.classList.add("tour-on");
    // presenting: only the section of this step stays at full strength
    Array.prototype.forEach.call(document.querySelectorAll(".tour-here"), function (n) { n.classList.remove("tour-here"); });
    var sec = node && node.closest ? (node.id === "top" ? document.querySelector(".view.lead") : node.closest("main > section, main > .view")) : null;
    if (sec) sec.classList.add("tour-here");
  }
  function tourUrl() {
    try {
      var q = new URLSearchParams(location.search);
      if (tourAt >= 0) q.set("tour", String(tourAt + 1)); else q.delete("tour");
      if (tourAt >= 0 && tourFull) q.set("full", "1"); else q.delete("full");
      var qs = q.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
    } catch (e) { /* sandboxed */ }
  }
  function tourGo(i) {
    if (!tourSteps.length) return;
    if (i >= tourSteps.length) { tourExit(); return; }
    tourAt = Math.max(0, i);
    var s = tourSteps[tourAt];
    tourShow();
    if (s.run) s.run(); else { closeInline(); if ($("cv-play").textContent === "Pause") $("cv-play").click(); scrollToEl(s.el()); }
    tourUrl(); tourArm();
  }
  // auto: advance by itself, longer on steps that play clips; any manual step keeps it running, Exit or the last step stops it
  var tourAuto = false, tourTimer = null;
  function tourArm() {
    clearTimeout(tourTimer); tourTimer = null;
    var b = $("tour-auto"); if (b) b.setAttribute("aria-pressed", String(tourAuto));
    if (!tourAuto || tourAt < 0) return;
    if (tourAt >= tourSteps.length - 1) { tourAuto = false; if (b) b.setAttribute("aria-pressed", "false"); return; }
    tourTimer = setTimeout(function () { tourGo(tourAt + 1); }, tourSteps[tourAt].run ? 12000 : 7000);
  }
  function tourExit() {
    tourAuto = false; tourArm(); closeInline();
    tourAt = -1; $("tour").hidden = true; document.body.classList.remove("touring");
    Array.prototype.forEach.call(document.querySelectorAll(".tour-on, .tour-here"), function (n) { n.classList.remove("tour-on"); n.classList.remove("tour-here"); });
    tourUrl();
  }
  function wireTour() {
    $("hero-tour").addEventListener("click", function () { tourStart(false); });
    $("hero-tour-full").addEventListener("click", function () { tourStart(true); });
    $("nav-tour").addEventListener("click", function () { if (tourAt >= 0) tourExit(); else tourStart(false); });
    $("tour-prev").addEventListener("click", function () { tourGo(tourAt - 1); });
    $("tour-next").addEventListener("click", function () { tourGo(tourAt + 1); });
    $("tour-exit").addEventListener("click", tourExit);
    $("tour-auto").addEventListener("click", function () { tourAuto = !tourAuto; tourArm(); });
    document.addEventListener("keydown", function (e) {
      if ((e.key === "f" || e.key === "F") && !e.altKey && !e.ctrlKey && !e.metaKey && !/^(SELECT|INPUT|TEXTAREA)$/.test(e.target && e.target.tagName || "")) {
        var open = document.querySelector(".st-play") || document.querySelector(".st-inplace video"); if (open) { e.preventDefault(); toggleFull(open); return; }
      }
      if (tourAt < 0 || e.altKey || e.ctrlKey || e.metaKey) return;
      var tg = e.target && e.target.tagName;
      if (tg === "SELECT" || tg === "INPUT" || tg === "TEXTAREA" || tg === "VIDEO") return;
      if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); tourGo(tourAt + 1); }
      else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); tourGo(tourAt - 1); }
      else if (e.key === "a" || e.key === "A") { tourAuto = !tourAuto; tourArm(); }
      else if (e.key === "Escape") tourExit();
    });
  }
  // nav: mark the section in view
  function wireSpy() {
    if (typeof IntersectionObserver !== "function") return;
    var links = {}; Array.prototype.forEach.call(document.querySelectorAll("nav.top a.nl"), function (a) { links[a.getAttribute("href").slice(1)] = a; });
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        for (var k in links) { if (k === e.target.id) links[k].setAttribute("aria-current", "true"); else links[k].removeAttribute("aria-current"); }
      });
    }, { rootMargin: "-30% 0px -65% 0px" });
    Object.keys(links).forEach(function (id) { var n = $(id); if (n) io.observe(n); });
  }
  // ?tour=N opens the tour at step N once the clips' manifests are in
  var tourWanted = 0, findingWanted = "";
  function tourFromUrl() {
    if (findingWanted) { var f = findingWanted; findingWanted = ""; openFinding(f); }
    if (!tourWanted) return; buildTour();
    var n = tourWanted; tourWanted = 0; tourGo(Math.min(n, tourSteps.length) - 1);
  }

  /* ---------- footer ---------- */
  function renderFoot() {
    var f = $("foot"); clear(f);
    function A(href, text) { return el("a", { href: href, target: "_blank", rel: "noopener", text: text }); }
    function T(t) { return document.createTextNode(t); }
    f.appendChild(el("h2", { class: "credhead", text: "Method" }));
    f.appendChild(el("p", { text: "Every score comes from PlayWorld's own verifier with Gemini 3.1 Pro at the benchmark's settings. Cheaper screening judges are never shown. The judge writes its comments mostly in Chinese; English copies are machine-translated for display after scoring, never feed a score, and the judge's original text is authoritative." }));
    f.appendChild(el("p", { text: "Model-side A/Bs use fixed action scripts or the scripted player; player-side A/Bs use the AI player. Both get 2 to 4 official judge passes, and a task counts as moved only when it changes by a full point. A final score needs the AI player, all 171 tasks and 2 or more passes." }));
    f.appendChild(el("p", null, [T("Rows come from "), A("https://github.com/" + REPO + "/blob/main/results/experiments.csv", "results/experiments.csv"), T(" (" + source + "). "), A("https://github.com/" + REPO, "Repository"), T(".")]));
    f.appendChild(el("h2", { class: "credhead", text: "Credits" }));
    var ul = el("ul", { class: "credits", "aria-label": "Credits" });
    function li(kids) { ul.appendChild(el("li", null, kids)); }
    li([el("b", { text: "PlayWorld" }), T(" benchmark, harness, verifier and task data: Ding et al., “PlayWorld: Benchmarking World Models with Agent Players over Long-Horizon Objectives”, "), A("https://arxiv.org/abs/2608.13552", "arXiv:2608.13552"), T(", "), A("https://github.com/kxding/PlayWorld", "code"), T(", "), A("https://huggingface.co/datasets/jocelynd/playworld-bench", "data"), T(". Task images come from Pexels and web image search and keep their sources’ terms.")]);
    li([el("b", { text: "LingBot-World v2" }), T(", Robbyant Team, “Infinite Worlds with Versatile Interactions”, "), A("https://arxiv.org/abs/2607.07534", "arXiv:2607.07534"), T(", "), A("https://github.com/Robbyant/lingbot-world-v2", "code"), T(", CC BY-NC-SA 4.0. Its weights and modules run unchanged at a pinned commit; "), A("https://github.com/" + REPO + "/blob/main/adapters/lingbot_world2/session.py", "our session wrapper"), T(" re-implements its causal sampling loop.")]);
    li([T("Reference scores for Genie 3 (Google DeepMind), SANA-WM (NVIDIA, "), A("https://github.com/NVlabs/Sana", "Sana"), T("), Matrix-Game 3.0 (Skywork AI, "), A("https://github.com/SkyworkAI/Matrix-Game", "Matrix-Game"), T(") and LingBot-World v2 are as reported in the PlayWorld paper.")]);
    li([T("Scoring: Gemini 3.1 Pro (Google) via the PlayWorld verifier. Agent player: OpenAI gpt-6-luna for compared runs; the 24-task baseline lb14-session-agent-dev-v1 used gpt-4.1-mini.")]);
    li([T("Team: "), A("https://github.com/benceruleanlu", "Benjamin Lu"), T(", "), A("https://github.com/Hcoder10", "Hari Gangadharan"), T(", "), A("https://github.com/jpoehnelt", "Justin Poehnelt"), T(", "), A("https://github.com/kevvzhang", "Kevv"), T(". Built at the "), A("https://iterate.inc/ai-research", "Iterate AI Research Hackathon"), T(", San Francisco, November 2026. Site built with "), A("https://astro.build", "Astro"), T(".")]);
    f.appendChild(ul);
  }

  /* ---------- explore tabs: compare player, one run's scenes, all tests, all runs ---------- */
  var MODES = [["compare", "tab-compare", "compare-clips"], ["scenes", "tab-scenes", "scenes"], ["tests", "tab-tests", "testing"], ["runs", "tab-runs", "runs"]];
  var mode = "compare";
  function modeOfHash(h) { var hit = MODES.filter(function (x) { return "#" + x[2] === h; })[0]; return hit ? hit[0] : ""; }
  function setMode(m, user) {
    mode = m;
    MODES.forEach(function (x) {
      var on = x[0] === m;
      $(x[1]).setAttribute("aria-selected", String(on));
      $(x[1]).setAttribute("tabindex", on ? "0" : "-1");
      $(x[2]).hidden = !on;
      if (!on) Array.prototype.forEach.call($(x[2]).querySelectorAll("video"), function (v) { if (!v.paused) v.pause(); });
    });
    // the clip footnote belongs to the two clip tabs
    var note = $("watch-note"); if (note) note.hidden = m !== "compare" && m !== "scenes";
    if (m !== "compare" && $("cv-play").textContent === "Pause") $("cv-play").click();
    if (!user) return;
    // the other clip tab's deep-link params would win on reload, so drop them
    try {
      var q = new URLSearchParams(location.search);
      (m === "compare" ? ["scenes", "scene"] : m === "scenes" ? ["compare", "a", "b", "c"] : ["scenes", "scene", "compare", "a", "b", "c"]).forEach(function (k) { q.delete(k); });
      var qs = q.toString(), panel = MODES.filter(function (x) { return x[0] === m; })[0][2];
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + "#" + panel);
    } catch (e) { /* sandboxed */ }
    // each clip tab writes its own selection back to the URL
    if (m === "scenes") syncUrl(); else if (m === "compare") document.dispatchEvent(new CustomEvent("pwa:mode", { detail: m }));
  }
  function initMode() {
    var q = new URLSearchParams(location.search);
    setMode(q.has("compare") ? "compare" : q.has("scenes") ? "scenes" : modeOfHash(location.hash) || "compare", false);
    MODES.forEach(function (x, i) {
      $(x[1]).addEventListener("click", function () { setMode(x[0], true); });
      $(x[1]).addEventListener("keydown", function (e) {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight" && e.key !== "Home" && e.key !== "End") return;
        e.preventDefault();
        var n = e.key === "Home" ? 0 : e.key === "End" ? MODES.length - 1 : (i + (e.key === "ArrowRight" ? 1 : MODES.length - 1)) % MODES.length;
        setMode(MODES[n][0], true); $(MODES[n][1]).focus();
      });
    });
    // a link to a panel that is not showing (#runs, #testing, ...) opens its tab first
    window.addEventListener("hashchange", function () {
      var m = modeOfHash(location.hash); if (m && m !== mode) { setMode(m, false); scrollToEl($("watch")); }
    });
  }

  /* ---------- scenes ---------- */
  var MEDIA_RAW = "https://raw.githubusercontent.com/" + REPO + "/main/results/media/";
  var scenesExp = "", scenesFam = "", scenesIdx = null, scenesMan = null, scenesAll = false, scenesDefault = "", SCENES_SHOWN = 4;
  // deep link ?scenes=EXP&scene=TASK: that one rollout, player open. scenesWanted remembers a run not (yet) in the index.
  var scenesTask = "", scenesWanted = "", scenesScrolled = false;
  // an index entry or manifest without `scored` predates unscored scenes: it was an official scored run
  function runScored(r) { return !r || r.scored !== false; }
  function runLabels(r) { return (r && r.labels) || []; }
  // the same deep link the workflow writes into the step summary and results/reports/ (pwa media watch_url)
  function sceneLink(exp, task) {
    var q = new URLSearchParams(); q.set("scenes", exp); if (task) q.set("scene", task);
    return location.pathname + "?" + q.toString() + "#scenes";
  }
  // ?media=DIR/ (same origin only, like ?csv=) reads index.json and the manifests from DIR instead of main
  function mediaOverride() {
    var q = new URLSearchParams(location.search).get("media");
    if (!q) return null;
    try { var u = new URL(q.replace(/\/?$/, "/"), location.href); return u.origin === location.origin ? u.href : null; } catch (e) { return null; }
  }
  // one fetch per file, shared with compare.js
  var JSON_CACHE = {};
  function getJson(name) {
    if (JSON_CACHE[name]) return JSON_CACHE[name];
    var ov = mediaOverride(), p;
    if (ov) p = get(ov + name, 6000).then(JSON.parse);
    else p = get(MEDIA_RAW + name, 6000).then(JSON.parse).catch(function () { return get("media/" + name, 6000).then(JSON.parse); });
    p.catch(function () { delete JSON_CACHE[name]; });
    return (JSON_CACHE[name] = p);
  }
  function sceneCard(t, open) {
    var famName = FAMINFO[t.family] ? FAMINFO[t.family].name : (t.family || "-");
    var media = el("div", { class: "media" });
    function player(focus) {
      var v = el("video", { controls: "", playsinline: "", preload: focus ? "none" : "metadata", src: t.video, poster: t.poster || null, "aria-label": "Rollout of " + t.task_id });
      v.muted = true;
      clear(media); media.appendChild(v);
      var pr = v.play(); if (pr && pr.catch) pr.catch(function () { /* autoplay refused: controls stay */ });
      if (focus) v.focus();
    }
    if (t.video && open) player(false);
    else if (t.video) {
      media.appendChild(el("img", { src: t.poster || "", alt: "First frames of " + t.task_id, loading: "lazy" }));
      var pb = el("button", { class: "play", type: "button", "aria-label": "Play " + t.task_id });
      pb.addEventListener("click", function () { player(true); });
      media.appendChild(pb);
    } else {
      if (t.poster) media.appendChild(el("img", { src: t.poster, alt: "First frames of " + t.task_id, loading: "lazy" }));
      media.appendChild(el("div", { class: "novid", text: "No video" }));
    }
    var st = t.status || [], ok = st.length === 1 && st[0] === "ok";
    var row = el("div", { class: "row" }, [
      el("b", { text: t.task_id }),
      el("span", { class: "sc", title: passesText(t), text: typeof t.mean === "number" ? fmt(t.mean) : (runScored(scenesMan) ? "unscored" : "no score") })
    ]);
    var row2 = el("div", { class: "row" }, [
      el("span", { class: "fam", text: famName }),
      el("span", { class: "badge " + (ok ? "ok" : "warn"), text: st.length ? st.join(", ") : "no status" })
    ]);
    var kids = [media, row, row2];
    if (t.video && /^https:/.test(t.video)) kids.push(el("div", { class: "row" }, [el("a", { class: "sclink", href: sceneLink(scenesExp, t.task_id), text: "Link to this scene" }),
      el("a", { class: "sclink", href: t.video, rel: "noopener", text: "Download mp4" })]));
    var jc = judgeComment(t, false); if (jc) kids.push(jc);
    return el("article", { class: "scene" }, kids);
  }
  // grouped run picker (runinfo.js): one optgroup per arm group, arms named by what they add
  var scenesMore = false;
  function fillRunSelect(sel, exps, current, showAll) {
    clear(sel);
    RI.options(exps, current, showAll).forEach(function (g) {
      var parent = sel;
      if (g.label) { parent = el("optgroup", { label: g.label }); sel.appendChild(parent); }
      g.options.forEach(function (o) { parent.appendChild(el("option", { value: o.value, text: o.text })); });
    });
    sel.value = current;
  }
  function renderSceneDesc() {
    var box = $("sc-desc"); if (!box) return; clear(box);
    var info = RI.get(scenesExp); if (!info) { box.hidden = true; return; }
    box.hidden = false;
    box.appendChild(el("b", { text: info.head }));
    box.appendChild(el("code", { class: "rawid", text: scenesExp }));
    box.appendChild(el("span", { class: "screst", text: info.rest }));
  }
  function renderScenes() {
    var grid = $("sc-grid"), empty = $("sc-empty"), filt2 = $("scenes-filters");
    if (!grid) return;
    clear(grid);
    var runs = scenesIdx && scenesIdx.runs ? scenesIdx.runs : [];
    var lb = $("sc-labels"); clear(lb); lb.hidden = true;
    if (!runs.length) {
      empty.hidden = false; empty.textContent = "No scenes published yet. Each run that generates videos adds them to a GitHub Release.";
      filt2.hidden = true; $("sc-files").hidden = true; return;
    }
    filt2.hidden = false;
    var rs = $("sc-run"), fs = $("sc-fam");
    fillRunSelect(rs, runs.map(function (r) { return r.exp; }), scenesExp, scenesMore);
    renderSceneDesc();
    var run = runs.filter(function (r) { return r.exp === scenesExp; })[0];
    if (run && run.release_url && /^https:/.test(run.release_url)) { $("sc-files").href = run.release_url; $("sc-files").hidden = false; } else $("sc-files").hidden = true;
    renderSceneModel();
    if (!scenesMan) { empty.hidden = false; empty.textContent = "Could not load the manifest for " + scenesExp + "."; return; }
    var labels = runLabels(scenesMan);
    if (scenesWanted && scenesWanted !== scenesExp) labels = ["no scenes for " + scenesWanted + " yet (they appear when its run finishes publishing); showing " + scenesExp].concat(labels);
    if (labels.length) {
      lb.hidden = false;
      labels.forEach(function (l) { lb.appendChild(el("span", { class: "badge warn", text: l })); });
    }
    var tasks = scenesMan.tasks || [];
    clear(fs); fs.appendChild(el("option", { value: "", text: "All families" }));
    FAMS.forEach(function (f) { var o = el("option", { value: f[0], text: FAMINFO[f[0]].name }); if (f[0] === scenesFam) o.selected = true; fs.appendChild(o); });
    var one = scenesTask ? tasks.filter(function (t) { return t.task_id === scenesTask; })[0] : null;
    if (one) {
      // deep link to one rollout: show it with the player open, and a way back to the whole run
      empty.hidden = true;
      grid.appendChild(sceneCard(one, true));
      var back = el("button", { class: "scmore", type: "button", text: "Show all " + tasks.length + " scenes of this run" });
      back.addEventListener("click", function () { scenesTask = ""; renderScenes(); syncUrl(); });
      grid.appendChild(el("div", { style: "grid-column:1/-1" }, [back]));
      if (!scenesScrolled) { scenesScrolled = true; var sec = $("scenes"); if (sec && sec.scrollIntoView) sec.scrollIntoView(); }
      return;
    }
    var list = tasks.filter(function (t) { return !scenesFam || t.family === scenesFam; });
    empty.hidden = list.length > 0; if (!list.length) empty.textContent = "No tasks in this family for this run.";
    var shown = scenesAll ? list : list.slice(0, SCENES_SHOWN);
    shown.forEach(function (t) { grid.appendChild(sceneCard(t)); });
    if (list.length > SCENES_SHOWN) {
      var b = el("button", { class: "scmore", type: "button", text: scenesAll ? "Show fewer" : "Show all " + list.length + " scenes" });
      b.addEventListener("click", function () { scenesAll = !scenesAll; renderScenes(); });
      grid.appendChild(el("div", { style: "grid-column:1/-1" }, [b]));
    }
  }
  var scenesReq = 0;
  function loadManifest() {
    // a response for a run the visitor has since switched away from is dropped, so cards always match the picker
    var req = ++scenesReq, exp = scenesExp;
    scenesMan = null; scenesAll = false;
    return getJson(exp + ".json").then(function (m) { if (req === scenesReq && m && m.exp === exp) scenesMan = m; })
      .catch(function () { if (req === scenesReq) scenesMan = null; });
  }
  // credit the model that generated this run's rollouts, from its manifest
  function renderSceneModel() {
    var box = $("sc-model"); if (!box) return; clear(box);
    var m = scenesMan && scenesMan.model; if (!m || !m.name) return;
    box.appendChild(document.createTextNode("Generated with "));
    if (m.url && /^https:/.test(m.url)) box.appendChild(el("a", { href: m.url, target: "_blank", rel: "noopener", text: m.name }));
    else box.appendChild(document.createTextNode(m.name));
    var who = [m.org, m.license].filter(Boolean).join(", ");
    box.appendChild(document.createTextNode((who ? " (" + who + ")" : "") + ". "));
  }
  function loadScenes() {
    return getJson("index.json").then(function (ix) {
      var runs = (ix && ix.runs) || [];
      runs.sort(function (a, b) { return a.generated < b.generated ? 1 : a.generated > b.generated ? -1 : 0; });
      scenesIdx = { runs: runs };
      // default: the newest official scored run with no labels, else the newest run
      var official = runs.filter(function (r) { return runScored(r) && !runLabels(r).length; });
      scenesDefault = official.length ? official[0].exp : (runs.length ? runs[0].exp : "");
      if (!runs.some(function (r) { return r.exp === scenesExp; })) { scenesWanted = scenesExp; scenesExp = scenesDefault; scenesTask = ""; }
      refreshRI();
      // every manifest, for task families and recorded flags in the run names
      Promise.all(runs.map(function (r) { return getJson(r.exp + ".json").then(function (m) { if (m && m.exp === r.exp) MANS[r.exp] = m; }, function () {}); }))
        .then(function () { refreshRI(); renderScenes(); renderBoard(); renderMethods(); renderStory(); renderGallery(); renderGlance(); renderFullResult(); document.dispatchEvent(new CustomEvent("pwa:runinfo")); tourFromUrl(); });
      return scenesExp ? loadManifest() : null;
    }).catch(function () { scenesIdx = null; }).then(function () { renderScenes(); renderBoard(); syncUrl(); });
  }
  function wireScenes() {
    $("sc-run").addEventListener("change", function (e) {
      if (e.target.value === RunInfo.MORE) { scenesMore = true; renderScenes(); $("sc-run").focus(); return; }
      scenesExp = e.target.value; scenesTask = ""; scenesWanted = "";
      var req = scenesReq + 1;
      loadManifest().then(function () { if (req === scenesReq) { renderScenes(); syncUrl(); } });
    });
    $("sc-fam").addEventListener("change", function (e) { scenesFam = e.target.value; scenesAll = false; scenesTask = ""; renderScenes(); syncUrl(); });
  }

  /* ---------- render all ---------- */
  function renderAll() {
    renderStatus(); renderVerdict(); renderGlance(); renderRuler(); renderFams(); renderFull(); renderFullResult(); renderStory(); renderGallery(); renderLoop(); renderTimeline(); renderMethods();
    renderToggles(); renderBoard();
    syncUrl();
    var top = $("top"); if (top) top.setAttribute("aria-busy", "false");
  }
  /* ---------- shareable URL state ---------- */
  function readUrl() {
    var q = new URLSearchParams(location.search);
    filt.tests = q.get("tests") === "1";
    filt.capped = q.get("capped") === "1";
    filt.ended = q.get("ended") === "1";
    var sv2 = q.get("sort") || "", d = sv2.charAt(0) === "-" ? -1 : 1, sk = sv2.replace(/^-/, "");
    if (COLS.some(function (c) { return c[0] === sk; })) { sort.key = sk; sort.dir = d; }
    tourWanted = Math.max(0, parseInt(q.get("tour") || "0", 10) || 0);
    if (q.get("auto") === "1") tourAuto = true;
    tourFull = q.get("full") === "1";
    findingWanted = q.get("finding") || "";
    scenesExp = q.get("scenes") || "";
    scenesTask = scenesExp ? (q.get("scene") || "") : "";
  }
  function syncUrl() {
    try {
      var q = new URLSearchParams(location.search);
      ["tests", "capped", "ended"].forEach(function (k) { if (filt[k]) q.set(k, "1"); else q.delete(k); });
      if (sort.key === "overall" && sort.dir < 0) q.delete("sort"); else q.set("sort", (sort.dir < 0 ? "-" : "") + sort.key);
      if (mode === "scenes") {
        if (scenesExp && (scenesExp !== scenesDefault || scenesTask)) q.set("scenes", scenesExp); else if (scenesDefault) q.delete("scenes");
        if (scenesTask) q.set("scene", scenesTask); else if (scenesIdx) q.delete("scene");
      }
      var qs = q.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
    } catch (e) { /* sandboxed or file: origins may refuse */ }
  }
  /* ---------- copy-link anchors on section headings ---------- */
  function addAnchors() {
    Array.prototype.forEach.call(document.querySelectorAll("section[id] > h2.sec"), function (h) {
      var id = h.parentNode.id, text = h.textContent;
      var wrap = el("div", { class: "sechead" });
      var a = el("a", { class: "anchor", href: "#" + id, "aria-label": "Link to " + text, text: "#" });
      var note = el("span", { class: "copied", role: "status", "aria-live": "polite" });
      var timer = null;
      h.parentNode.insertBefore(wrap, h); wrap.appendChild(h); wrap.appendChild(a); wrap.appendChild(note);
      a.addEventListener("click", function (e) {
        if (!(navigator.clipboard && navigator.clipboard.writeText)) return;
        e.preventDefault();
        var url = location.origin + location.pathname + location.search + "#" + id;
        navigator.clipboard.writeText(url).then(function () {
          history.replaceState(null, "", location.pathname + location.search + "#" + id);
          note.textContent = "Copied"; clearTimeout(timer);
          timer = setTimeout(function () { note.textContent = ""; }, 1800);
        }, function () { location.hash = id; });
      });
    });
  }
  function wire() {
    ["tests", "capped", "ended"].forEach(function (k) {
      $("f-" + k).addEventListener("change", function (e) { filt[k] = e.target.checked; renderBoard(); syncUrl(); });
    });
    $("runs-more").addEventListener("click", function () { runsAll = !runsAll; renderBoard(); if (!runsAll) scrollToEl($("watch")); });
    var rz = null, lastW = window.innerWidth;
    window.addEventListener("resize", function () {
      if (window.innerWidth === lastW) return; lastW = window.innerWidth;
      clearTimeout(rz); rz = setTimeout(function () { renderRuler(); renderTimeline(); }, 120);
    });
  }

  /* ---------- load ---------- */
  function get(url, ms) {
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, ms);
    return fetch(url, { cache: "no-store", signal: ctl ? ctl.signal : undefined }).then(function (r) {
      clearTimeout(timer);
      if (!r.ok) throw new Error("http " + r.status);
      return r.text();
    });
  }
  function override() {
    var q = new URLSearchParams(location.search).get("csv");
    if (!q) return null;
    try { var u = new URL(q, location.href); return u.origin === location.origin ? u.href : null; } catch (e) { return null; }
  }
  function load() {
    var ov = override();
    var first = ov ? get(ov, 6000).then(function (t) { return { t: t, s: "sample file " + ov }; })
      : get(RAW, 6000).then(function (t) { return { t: t, s: "live from the main branch (fetched " + new Date().toUTCString().slice(5, 22) + " UTC)" }; });
    return first.then(function (o) { return { rows: toRows(o.t), s: o.s }; }).catch(function () {
      return get("experiments.csv", 6000).then(function (t) { return { rows: toRows(t), s: "bundled snapshot (live fetch from GitHub failed)" }; });
    });
  }
  initMode(); wire(); wireScenes(); wireTour(); wireSpy(); addAnchors();
  load().then(function (o) { ALL = o.rows; source = o.s; refreshRI(); })
    .catch(function () { ALL = []; source = "unavailable: could not load the live or the bundled CSV"; })
    .then(function () { readUrl(); renderFoot(); renderAll(); renderTrail(); loadScenes(); shareData(); });
  // hand the loaded rows and shared helpers to the Compare player (src/scripts/compare.js)
  function shareData() {
    window.PWA_SITE = { rows: ALL, getJson: getJson, famName: function (f) { return FAMINFO[f] ? FAMINFO[f].name : (f || "-"); },
      isCapped: isCapped, isScripted: isScripted, isSmoke: isSmoke, isOpen: isOpen, isClosed: isClosed, fmt: fmt,
      runInfo: function () { return RI; } };
    document.dispatchEvent(new CustomEvent("pwa:data"));
  }
})();
