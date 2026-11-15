// Client-side results page: fetches results/experiments.csv from main at view time.
import * as RunInfo from "./runinfo.js";
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
  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "text") e.textContent = attrs[k];
      else if (k === "class") e.className = attrs[k];
      else if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c) e.appendChild(c); });
    return e;
  }
  // The judge's reason: the English display copy (translated after scoring) with a toggle for the judge's original,
  // which is authoritative; the original alone, marked untranslated, when no copy exists.
  // A failing pass (gate, IF/OE check, error) that is not the representative one keeps its own reason under it.
  function judgeComment(t, open) {
    if (!t.reason) return null;
    var attrs = open ? { open: "" } : null;
    var failSt = (t.status || []).filter(function (s) { return s !== "ok"; }).join(", ") || "failed";
    var failHead = t.fail_reason ? "Pass " + (t.fail_pass === null || t.fail_pass === undefined ? "?" : t.fail_pass) + " (" + failSt + "): " : "";
    if (t.reason_en) {
      var origs = [el("p", { class: "jorig", text: t.reason })];
      var kids = [el("summary", { text: "Judge's comment (translated from the judge's original)" }), el("p", { text: t.reason_en })];
      if (t.fail_reason) {
        kids.push(el("p", { class: "jfail", text: failHead + (t.fail_reason_en || t.fail_reason) }));
        if (t.fail_reason_en) origs.push(el("p", { class: "jorig", text: failHead + t.fail_reason }));
      }
      origs.forEach(function (o) { o.hidden = true; });
      var btn = el("button", { type: "button", class: "jtoggle", "aria-expanded": "false", text: "show original" });
      btn.addEventListener("click", function () {
        var hide = !origs[0].hidden;
        origs.forEach(function (o) { o.hidden = hide; });
        btn.textContent = hide ? "show original" : "hide original";
        btn.setAttribute("aria-expanded", hide ? "false" : "true");
      });
      return el("details", attrs, kids.concat([btn]).concat(origs));
    }
    var plain = [el("summary", { text: "Judge's comment" }), el("p", { text: t.reason })];
    if (t.fail_reason) plain.push(el("p", { class: "jfail", text: failHead + t.fail_reason }));
    plain.push(el("p", { class: "jnote", text: "judge's own words, untranslated" }));
    return el("details", attrs, plain);
  }
  function passesText(t) {
    var ps = t.pass_scores || [];
    return ps.length ? "per pass " + ps.map(function (v) { return typeof v === "number" ? String(Math.round(v * 100) / 100) : "-"; }).join("/") : null;
  }
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
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function fmt(x, d) { return typeof x === "number" ? x.toFixed(d === undefined ? 2 : d) : "-"; }
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
  var PLAYER_NOTE = { "lb14-session-agent-dev-v1": "Older AI player than every run compared since, so this is a diagnostic, not the starting-model number." };
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
      box.appendChild(el("p", { class: "vs" }, [el("b", { text: shown.exp }), document.createTextNode(shown.notes ? ": " + shown.notes : "")]));
      if (PLAYER_NOTE[shown.exp]) box.appendChild(el("p", { class: "vs", text: PLAYER_NOTE[shown.exp] }));
    } else box.appendChild(el("p", { class: "vs", text: "No run big enough to estimate a score yet (24 or more tasks, 2 or more judge passes)." }));
    var lb = REFS.filter(function (r) { return r.exp === "LingBot-World2"; })[0];
    box.appendChild(el("p", { class: "vs", text: "Paper, all 171 tasks: Genie 3 " + fmt(GENIE.overall) + ", LingBot-World v2 " + fmt(lb.overall) + "." }));
  }
  function renderFull() {
    var full = realRows().filter(function (r) { return isFull(r) && r.overall !== null; });
    var most = 0; realRows().forEach(function (r) { if (r.overall !== null && r.n_tasks > most) most = r.n_tasks; });
    $("full").textContent = full.length ? "" : "No full-benchmark score exists yet: every scored run so far covers at most " + most + " of the " + FULL_TASKS + " tasks, so none compares directly with the paper rows.";
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
    var t = $("fams"); clear(t);
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
    gc: { name: "Geometry consistency", q: "layout holds as the camera moves" },
    if: { name: "Interaction fidelity", q: "each action does what was asked" },
    insight: { name: "Insight evolution", q: "an on-screen process keeps going" },
    outsight: { name: "Out-of-sight evolution", q: "hidden things change sensibly" }
  };
  // group: now (model-side A/B) | parked (player-side, tried) | cand (merged or proposed, unscored)
  // arms: [label, exp] pairs read from results/experiments.csv; the first is the control. cells: per-task readout from results/reports/.
  var METHODS = [
    { group: "now", title: "Turn calibration", arms: [["off", "fx14-model-dev-v2-a1"], ["on", "fx14-model-dev-v2-a2"]],
      body: "One turn key turns the angle the task prompt names (22.5 degrees sideways, 20 up or down) instead of the default 34 and 11.",
      links: [["#23", PR + "23"]] },
    { group: "now", title: "Caption prompt", arms: [["off", "fx14-model-dev-v2-a2"], ["on", "fx14-model-dev-v2-a3"]], also: ["ins14-base-v2", "ins14-caption-v1"],
      body: "Conditions the model on the task's scene caption instead of the player goal, which reads \"wait and observe\" on 29 of 30 insight tasks. Earlier ins14 runs (closed-loop harness, but insight tasks are wait-only, so the player is never called): the control ins14-base-v2 was generated, and the caption arm ins14-caption-v1 was cancelled.",
      links: [["#32", PR + "32"], ["#63", PR + "63"]] },
    { group: "now", title: "Insight director, IF slow translation (re-anchor on, cannot fire with fixed actions)", arms: [["without", "fx14-model-dev-v2-a3"], ["with", "fx14-model-dev-v2-a4"]],
      body: "Adds an insight prompt cue and half-speed camera translation on IF tasks, on top of the caption prompt. Re-anchoring is switched on in the second arm, but fixed action scripts replay each task as one call, so it never fires there; its test is the scripted-player GC A/B below.",
      links: [["#46", PR + "46"], ["#90", PR + "90"]] },
    { group: "now", title: "Conditioning strength per denoising step", arms: [["control", "cs14-fx-v1-a1"], ["schedule", "cs14-fx-v1-a2"], ["+ text 1.0", "cs14-fx-v1-a3"], ["early 4", "cs14-fx-v1-a4"]],
      body: "Scales camera and text conditioning on the early denoising steps of stationary and third-person chunks and restores it on the late steps. All four arms have the caption prompt and turn calibration on.",
      links: [["#101", PR + "101"]] },
    { group: "now", title: "Camera-conditioning weight modulation", arms: [["control", "wm14-fx-v1-a1"], ["weight-mod", "wm14-fx-v1-a2"]], also: ["wm14-ctl-c10-v1", "wm14-arm-c10-v1"],
      body: "Scales how strongly the model follows the camera command, per chunk: off on still chunks, slightly lower on moving third-person chunks. Both arms have the caption prompt and turn calibration on. The earlier c10 runs were capped smoke checks from the PR branch.",
      links: [["#87", PR + "87"], ["#104", PR + "104"]] },
    { group: "now", title: "IF identity cue", arms: [["control", "wm14-fx-v1-a1"], ["cue", "wm14-fx-v1-a3"]],
      body: "Appends a fixed sentence about keeping each subject's identity to the model prompt on third-person IF tasks.",
      links: [["#104", PR + "104"]] },
    { group: "now", title: "Attention window: larger sink", arms: [["control", "mem14-fx-v1-a1"], ["sink 12", "mem14-fx-v1-a2"]], also: ["mem14-fx-v1-a3", "mem14-fx-v1-a4"],
      cells: "OE039 up 1.5, OE048 down 1.9",
      body: "Changes how many latent frames the model keeps attending to (sink 6 and local window 18 by default), which sets how far back it remembers. Both arms have the caption prompt and turn calibration on. The two arms with a local window of 36 failed and have no score.",
      links: [["#104", PR + "104"]] },
    { group: "now", title: "Pose memory", arms: [["control", "pm14-fx-v1-a1"], ["memory", "pm14-fx-v1-a2"], ["memory, wider window", "pm14-fx-v1-a3"], ["wider window only", "pm14-fx-v2-a4"]],
      also: ["pm14-fx-v2-a1", "pm14-fx-v2-a2", "pm14-fx-v2-a3"],
      body: "Stores each generated chunk by its commanded camera pose and re-inserts the most recent matching view into the attention sink when the camera comes back to it. The wider window (sink 10, local 22) is the control for the arm that recalls two chunks. Three more variants (opening kept to 1 latent, re-timed memory, yaw gain 0.85) ran against the same control.",
      links: [["findings", "#story-memory"]] },
    { group: "now", title: "Sink key scale", arms: [["control", "sks14-fx-v1-a1"], ["0.7", "sks14-fx-v1-a2"], ["0.4", "sks14-fx-v1-a3"], ["0.7 from chunk 4", "sks14-fx-v1-a4"]],
      body: "Scales down the attention keys of the pinned opening frames on later chunks. Out-of-sight tasks only; every arm scored below control.",
      links: [["findings", "#story-sink"]] },
    { group: "now", title: "Insight prompt: goal, caption, caption with cue", arms: [["goal prompt", "ins14-fx-v2-a1"], ["caption", "ins14-fx-v2-a2"], ["caption + director", "ins14-fx-v2-a3"]],
      body: "All six insight dev tasks. Insight tasks are wait-only, so the fixed-action rollout equals the closed-loop one.",
      links: [["#32", PR + "32"], ["#90", PR + "90"]] },
    { group: "now", title: "GC chunk-level flags (scripted player)", arms: [["control", "sp14-gc-v1-a1"], ["chunk director", "sp14-gc-v1-a2"], ["ease turns", "sp14-gc-v1-a3"], ["re-anchor", "sp14-gc-v1-a4"]],
      body: "The scripted player replays the dataset moves chunk by chunk, so flags that act per chunk can fire. Not a closed-loop score.",
      links: [["#100", PR + "100"], ["#102", PR + "102"]] },
    { group: "parked", title: "Return stop", arms: [["off", "rs13-arms-v1-a1"], ["on", "rs13-arms-v1-a2"]], cells: "2 of 3 GC tasks up a full point, 0 of 3 out-of-sight",
      body: "Ends the rollout once the commanded camera has left and come back to the start. 1.3B model, one run per side, player hint and turn calibration on in both.",
      links: [["#75", PR + "75"]] },
    { group: "parked", title: "GC completion hint", arms: [["off", "gch13-arms-v1-a1"], ["on", "gch13-arms-v1-a2"]], cells: "2 of 3 tasks down a full point",
      body: "Tells the player to run the camera path once and end. 1.3B model, one run per side. It ran before the player's empty-reply fix (#89).",
      links: [["#78", PR + "78"], ["#89", PR + "89"]] },
    { group: "parked", title: "Player hint", arms: [["no flags", "smk14-arms-gc-v2-a1"], ["turn cal + hint", "smk14-arms-gc-v2-a2"]],
      body: "Tells the player how far one action turns the camera and where the commanded camera is. Turn calibration is also on in the second arm. Only capped smoke runs exist, which never count as scores.",
      links: [["#59", PR + "59"]] },
    { group: "cand", title: "Proposal batch 2: IF horizon, IF camera hint, history endpoints, IF repeat check",
      body: "Merged behind opt-in flags. Its insight director and IF slow translation are in the model-side runs above.", links: [["#90", PR + "90"]] },
    { group: "cand", title: "Proposal batch 3: IF subject director",
      body: "Merged behind opt-in flags. The batch's GC chunk director and GC ease turns are in the scripted-player GC A/B above.", links: [["#100", PR + "100"]] },
    { group: "cand", title: "Proposal batch 4: weight-modulation knobs, measured turn",
      body: "Merged behind opt-in flags and not run yet. Weight modulation, the IF identity cue and the attention window are under test above.", links: [["#104", PR + "104"]] }
  ];
  var GROUPS = [
    ["now", "Testing now: model-side", "Fixed action scripts or the scripted player (no AI player), 14B model, official judge, 4 passes."],
    ["parked", "Tried and parked: player-side", "AI player, official judge, 4 passes, small task sets. Not adopted."],
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
      var s = rows.length === 2 ? fmt(rows[0].overall) + " → " + fmt(rows[1].overall) + " overall, " + rows[1].n_tasks + " tasks"
        : m.arms.map(function (a, i) { return a[0] + " " + fmt(rows[i].overall); }).join(" · ");
      return { text: s + (m.cells ? "; " + m.cells : ""), none: false };
    }
    if (rows.some(function (r) { return r && isCapped(r); })) return { text: "capped smoke only, no decision", none: true };
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
    { id: "player", kind: "note", kicker: "Starting point", title: "With an AI player, the player decides most camera tasks",
      body: "In our 24-task baseline the player reversed direction 9 to 17 times on every out-of-sight task and 25 times on GC036. On 4 of 6 out-of-sight tasks the camera never came back to the start view, so there was nothing for the judge to grade. We therefore test model-side changes with fixed action scripts, and keep the AI player for final scores.",
      say: "The baseline player turned left and right for the whole rollout. Model-side tests use fixed moves instead.",
      scene: ["lb14-session-agent-dev-v1", "GC036"], sceneLabel: "Watch the baseline player on GC036",
      links: [["baseline census", BLOB + "research/baseline-census.md"]] },
    { id: "noise", kind: "repeat", kicker: "Noise floor", title: "The same settings, scored three times, do not give the same score",
      body: "Three control arms ran the same flags and the same fixed action scripts, at different commits. Their per-task means over four judge passes still differ. So a task counts as moved only at a full point, and a change is adopted only if the gain repeats on a second seed.",
      say: "Three identical controls disagree. That sets the bar: a full point, twice.",
      runs: [["run 1", "pm14-fx-v1-a1"], ["run 2", "sks14-fx-v1-a1"], ["run 3", "mem14-fx-v1-a1"]],
      watch: { task: "OE047", b: "pm14-fx-v1-a1", c: "sks14-fx-v1-a1" }, watchLabel: "Watch two identical controls on OE047" },
    { id: "turncal", kicker: "Camera", title: "Given correct moves, calibrated turns lifted two GC tasks by more than a point",
      body: "The task prompts name angles (a turn key is 22.5 degrees) but the model's default rate turns 34. With dataset moves replayed and the rate calibrated, GC031 and GC036 moved up. In the separate 24-task A/B the same two tasks moved by 0.35 and 0.80, under the bar, so this is not adopted.",
      say: "Calibrated turns: two tasks up on one run, under the bar on the second.",
      ctl: "orc14-gc-v1-a1", arms: [["turn cal", "orc14-gc-v1-a2", "turn calibration"]],
      watch: { task: "GC031", b: "orc14-gc-v1-a1", c: "orc14-gc-v1-a2" } },
    { id: "memory", kicker: "Memory", title: "Pose memory did not beat its control. A wider attention window did, on one task",
      body: "The model attends to about two seconds of recent frames plus its opening frames. Pose memory re-inserts an earlier view when the camera comes back to it. Alone it moved no task up. Widening the window moved OE039 up by 1.9, with or without the memory, and a third run with a larger sink moved it by 1.5. The larger sink also dropped OE048 in two of those three runs.",
      say: "Our memory mechanism did not help. Simply widening the window did, on one task.",
      ctl: "pm14-fx-v1-a1", arms: [["memory", "pm14-fx-v1-a2", "pose memory"], ["window", "pm14-fx-v2-a4", "wider window (sink 10, local 22)"], ["both", "pm14-fx-v1-a3", "pose memory in the wider window"]],
      watch: { task: "OE039", b: "pm14-fx-v1-a1", c: "pm14-fx-v2-a4" } },
    { id: "sink", kicker: "Negative result", title: "Damping attention to the opening frames made out-of-sight worse",
      body: "Hypothesis: the pinned opening frames pull the scene back to its first state when the camera returns, which the rubric scores lowest. Scaling their attention keys down did not help in any of three arms.",
      say: "A hypothesis that failed: every arm scored lower than control.",
      ctl: "sks14-fx-v1-a1", arms: [["0.7", "sks14-fx-v1-a2", "key scale 0.7"], ["0.4", "sks14-fx-v1-a3", "key scale 0.4"], ["0.7 early", "sks14-fx-v1-a4", "key scale 0.7 from chunk 4"]],
      watch: { task: "OE048", b: "sks14-fx-v1-a1", c: "sks14-fx-v1-a4" } },
    { id: "insight", kicker: "Insight", title: "Does the scene caption wake up a static scene?", pending: true,
      body: "Insight tasks tell the player to wait and observe, and the model receives that sentence as its text prompt. In the baseline, four of six insight rollouts were flagged static. This A/B gives the model the task's scene caption instead, with and without a fixed activity cue.",
      say: "Insight: the model was being prompted with \"wait and observe\". This A/B swaps in the scene caption.",
      ctl: "ins14-fx-v2-a1", arms: [["caption", "ins14-fx-v2-a2", "caption prompt"], ["+ cue", "ins14-fx-v2-a3", "caption prompt and insight director"]],
      watch: { task: "OE018", b: "ins14-fx-v2-a1", c: "ins14-fx-v2-a3" } }
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
  function numCell(t, cls) {
    var v = cellVal(t), td = el("td", { class: "num" + (cls ? " " + cls : "") });
    if (v === null) { td.appendChild(el("span", { class: "dash", title: t ? "No judged clip for this task in this run" : null, text: t ? "no clip" : "-" })); return td; }
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
          b.addEventListener("click", function () { watch({ task: k, b: s.ctl, c: a[1] }); });
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
      cap: "Mean of the official judge's passes per task. ▲ ▼ mark a move of a full point against control. Click a number to watch that pair." };
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
      document.createTextNode(" on " + worst.k + "; " + over + " of " + ids.length + " tasks differ by 0.5 or more.")])]);
    return { table: el("table", { class: "ev" }, [el("thead", null, [hr]), tb]), sum: sum, gate: anyGate,
      cap: "Mean of the official judge's passes per task, for runs with identical settings." };
  }
  function storyState(s) {
    if (s.kind === "note") return "ok";
    var exps = s.kind === "repeat" ? s.runs.map(function (r) { return r[1]; }) : [s.ctl].concat(s.arms.map(function (a) { return a[1]; }));
    if (exps.some(function (e) { return tasksOfRun(e); })) return "ok";
    var rows = exps.map(rowByExp).filter(Boolean);
    if (rows.some(function (r) { return r.overall !== null; })) return "loading";
    if (rows.some(function (r) { return r.status === "running" && !isStale(r); })) return "running";
    if (rows.some(function (r) { return r.status === "generated"; })) return "generated";
    return rows.length ? "ended" : "none";
  }
  var storyShown = [];
  function renderStory() {
    var ol = $("story-list"); if (!ol) return; clear(ol); storyShown = [];
    STORY.forEach(function (s) {
      var st = storyState(s);
      // a finding whose runs ended without a score is not a finding; one still running is shown as pending
      if (st === "ended" || st === "none" || (st === "generated" && !s.pending)) return;
      var ev = st !== "ok" ? null : s.kind === "repeat" ? repeatEvidence(s) : s.kind === "note" ? null : abEvidence(s);
      var n = storyShown.length + 1;
      var text = el("div", { class: "st-text" }, [
        el("p", { class: "st-kick" }, [el("span", { class: "st-n", text: String(n) }), document.createTextNode(s.kicker)]),
        el("h3", { text: s.title }), el("p", { class: "st-body", text: s.body })]);
      var acts = el("p", { class: "st-acts" });
      if (s.watch && ev) {
        var wb = el("button", { type: "button", class: "cvbtn primary", text: s.watchLabel || "Watch " + s.watch.task + " side by side" });
        wb.addEventListener("click", function () { watch(s.watch); }); acts.appendChild(wb);
      }
      if (s.scene && MANS[s.scene[0]]) {
        var sb = el("button", { type: "button", class: "cvbtn primary", text: s.sceneLabel || "Watch " + s.scene[1] });
        sb.addEventListener("click", function () { openScene(s.scene[0], s.scene[1]); }); acts.appendChild(sb);
      }
      (s.links || []).forEach(function (l) { acts.appendChild(el("a", { href: l[1], target: "_blank", rel: "noopener", text: l[0] })); });
      if (acts.firstChild) text.appendChild(acts);
      var side = el("div", { class: "st-ev" });
      if (ev) {
        side.appendChild(ev.table); side.appendChild(ev.sum);
        side.appendChild(el("p", { class: "st-cap", text: ev.cap + (ev.gate ? " ✕ failed a gate in at least one pass." : "") }));
        var bd = el("div", { class: "badges" });
        var exps = s.kind === "repeat" ? s.runs.map(function (r) { return r[1]; }) : [s.ctl].concat(s.arms.map(function (a) { return a[1]; }));
        var rows = exps.map(rowByExp).filter(Boolean);
        if (rows.some(isOpen)) bd.appendChild(el("span", { class: "badge warn", title: "Fixed action scripts from the dataset, no AI player. Used for A/B tests only, never for final scores.", text: "open loop, A/B only" }));
        if (s.kind !== "repeat") bd.appendChild(el("span", { class: "badge warn", title: "One generation per arm. The adoption rule asks for the gain to repeat on a second seed.", text: "one seed" }));
        var ps = rows.map(function (r) { return r.passes; }).filter(function (p) { return p !== null; });
        if (ps.length) bd.appendChild(el("span", { class: "badge", text: Math.min.apply(null, ps) + " judge passes" }));
        side.appendChild(bd);
      } else if (s.kind !== "note") {
        side.appendChild(el("p", { class: "st-pend" }, [el("span", { class: "badge " + (st === "running" ? "warn" : ""), text: st === "running" ? "running now" : st === "generated" ? "generated, not scored yet" : "loading scores" }),
          document.createTextNode(" The per-task scores appear here when the official judge has scored every arm.")]));
      } else if (s.scene) {
        var t0 = MANS[s.scene[0]] && (MANS[s.scene[0]].tasks || []).filter(function (t) { return t.task_id === s.scene[1]; })[0];
        if (t0 && t0.poster) {
          var pb = el("button", { type: "button", class: "st-poster", "aria-label": s.sceneLabel || "Watch " + s.scene[1] }, [el("img", { src: t0.poster, alt: "", loading: "lazy" })]);
          pb.addEventListener("click", function () { openScene(s.scene[0], s.scene[1]); });
          side.appendChild(pb);
        }
      }
      var li = el("li", { class: "st card" + (ev || s.kind === "note" ? "" : " pend"), id: "story-" + s.id }, [text, side]);
      ol.appendChild(li); storyShown.push({ s: s, li: li, ev: !!ev });
    });
    if (!storyShown.length) ol.appendChild(el("li", { class: "empty", text: "No findings to show yet." }));
    buildTour();
  }

  /* ---------- hero: verdict line and the project in numbers ---------- */
  function renderVerdict() {
    var p = $("verdict"); if (!p) return; clear(p);
    var fin = bestFinal(), shown = fin || bestClosed();
    if (!shown) { p.hidden = true; return; }
    p.hidden = false;
    var beat = fin && fin.overall - TARGET >= 2 * (fin.overall_std || FALLBACK_STD);
    p.appendChild(el("b", { text: fin ? (beat ? "Answer: yes. " : "Answer: no. ") : "Answer so far: not yet. " }));
    p.appendChild(document.createTextNode(fin ? "Final score " + fmt(fin.overall) + " on all " + FULL_TASKS + " tasks against Genie 3's " + fmt(TARGET) + "."
      : "Our best official score is " + fmt(shown.overall) + " on " + shown.n_tasks + " of " + FULL_TASKS + " tasks; Genie 3 scores " + fmt(TARGET) + " on all of them. " +
        (ADOPTED.length ? "Adopted so far: " + ADOPTED.join(", ") + "." : "No change has yet repeated a full-point gain on two seeds, so none is adopted.")));
  }
  function renderGlance() {
    var ul = $("glance"); if (!ul) return; clear(ul);
    var real = realRows(), scored = real.filter(function (r) { return r.overall !== null; });
    var groups = {}; real.forEach(function (r) { var m = /\[arm \d+\/\d+ of ([^:\]]+)/.exec(r.notes || ""); if (m) groups[m[1]] = 1; });
    var judged = 0; scored.forEach(function (r) { judged += (r.n_tasks || 0) * (r.passes || 0); });
    var clipsN = 0; ((scenesIdx && scenesIdx.runs) || []).forEach(function (r) { clipsN += r.n_tasks || 0; });
    [[real.length, "runs logged", "Every launch writes a row, including failed and cancelled ones."],
     [Object.keys(groups).length, "A/B groups", "Sets of arms run on the same tasks and seed in one job."],
     [judged, "official judgments", "Task scores from Gemini 3.1 Pro: tasks times judge passes over every scored run."],
     [clipsN || null, "clips published", "Rollouts you can watch on this page."]].forEach(function (x) {
      if (x[0] === null) return;
      ul.appendChild(el("li", { title: x[2] }, [el("b", { text: String(x[0]) }), el("span", { text: x[1] })]));
    });
  }

  /* ---------- how a test runs ---------- */
  var LOOP = [
    ["Flag", "Each change is a runner flag, off by default, with a counter in the log that shows whether it fired.", "adapters/lingbot_world2/", "adapters/lingbot_world2"],
    ["Arms", "One job runs every arm on the same tasks and seed on Modal H100s; the model loads once per container.", "arms workflow", ".github/workflows/arms.yml"],
    ["Judge", "PlayWorld's own verifier, Gemini 3.1 Pro at the benchmark's settings, four passes per clip.", "pwa score", "pwa/score.py"],
    ["Decide", "A task moves only at a full point on its pass mean. A change is adopted only if the gain repeats on a second seed and no gate breaks.", "plan of record", "AGENTS.md#plan-of-record"],
    ["Publish", "The row, the judge's reason for every task and the clips land on main; this page reads them at view time.", "results/", "results"]
  ];
  function renderLoop() {
    var ol = $("loop-steps"); if (!ol) return; clear(ol);
    LOOP.forEach(function (x, i) {
      ol.appendChild(el("li", { class: "card" }, [el("div", { class: "lp-h" }, [el("span", { class: "st-n", text: String(i + 1) }), el("b", { text: x[0] })]),
        el("p", { text: x[1] }), el("a", { href: (/\.|#/.test(x[3]) ? BLOB : "https://github.com/" + REPO + "/tree/main/") + x[3], target: "_blank", rel: "noopener", text: x[2] })]));
    });
    var note = $("loop-note"); clear(note);
    note.appendChild(document.createTextNode("Measured: loading the 14B model fell from about 207 s to about 31 s with bit-identical weights ("));
    note.appendChild(el("a", { href: PR + "79", target: "_blank", rel: "noopener", text: "PR #79" }));
    note.appendChild(document.createTextNode("). Not covered by CI: GPU generation, Gemini scoring and player calls need keys."));
  }

  /* ---------- guided tour: a bar that walks the page in order; arrow keys step, Esc exits, ?tour=N deep links ---------- */
  var tourSteps = [], tourAt = -1;
  function buildTour() {
    var shown = bestFinal() || bestClosed();
    var steps = [{ el: function () { return $("top"); }, title: "The question", line: "Can inference-time changes lift an open world model past Genie 3 (" + fmt(TARGET) + ") on PlayWorld? No retraining." }];
    steps.push({ el: function () { return $("scores"); }, title: "Where we start",
      line: shown ? "The unmodified model, AI played: " + fmt(shown.overall) + " on " + shown.n_tasks + " tasks. Genie 3: " + fmt(TARGET) + " on all " + FULL_TASKS + "." : "No run big enough to estimate a score yet." });
    storyShown.forEach(function (x) {
      var s = x.s;
      steps.push({ el: function () { return x.li; }, title: s.title, line: s.say || "" });
      if (s.watch && x.ev) steps.push({ el: function () { return $("watch"); }, run: function () { watch(s.watch); }, title: "Watch " + s.watch.task, line: "Control on the left, treatment on the right, on one clock. The judge's score and comment are under each clip." });
      else if (s.scene && MANS[s.scene[0]]) steps.push({ el: function () { return $("watch"); }, run: function () { openScene(s.scene[0], s.scene[1]); }, title: "Watch " + s.scene[1], line: "One rollout, as the judge saw it." });
    });
    steps.push({ el: function () { return $("loop"); }, title: "How a test runs", line: "One dispatch: flag, arms on GPUs, official judge, full-point rule, published clips." });
    steps.push({ el: function () { return $("testing"); }, title: "Every change we tested", line: "Each row is an A/B with its runs. Nothing is hidden, including what failed." });
    steps.push({ el: function () { return $("runs"); }, title: "Every run", line: "The full log, with the commit and job behind each row." });
    tourSteps = steps;
    if (tourAt >= 0) tourShow();
  }
  function tourShow() {
    var bar = $("tour"), s = tourSteps[tourAt]; if (!bar || !s) return;
    bar.hidden = false; document.body.classList.add("touring");
    $("tour-n").textContent = (tourAt + 1) + " / " + tourSteps.length;
    $("tour-title").textContent = s.title; $("tour-line").textContent = s.line;
    $("tour-prev").disabled = tourAt === 0;
    $("tour-next").textContent = tourAt === tourSteps.length - 1 ? "Done" : "Next →";
    Array.prototype.forEach.call(document.querySelectorAll(".tour-on"), function (n) { n.classList.remove("tour-on"); });
    var node = s.el(); if (node && node.classList && node.id !== "top") node.classList.add("tour-on");
  }
  function tourUrl() {
    try {
      var q = new URLSearchParams(location.search);
      if (tourAt >= 0) q.set("tour", String(tourAt + 1)); else q.delete("tour");
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
    if (s.run) s.run(); else { if ($("cv-play").textContent === "Pause") $("cv-play").click(); scrollToEl(s.el()); }
    tourUrl();
  }
  function tourExit() {
    tourAt = -1; $("tour").hidden = true; document.body.classList.remove("touring");
    Array.prototype.forEach.call(document.querySelectorAll(".tour-on"), function (n) { n.classList.remove("tour-on"); });
    tourUrl();
  }
  function wireTour() {
    $("hero-tour").addEventListener("click", function () { tourGo(0); $("tour-next").focus(); });
    $("nav-tour").addEventListener("click", function () { if (tourAt >= 0) tourExit(); else { tourGo(0); $("tour-next").focus(); } });
    $("tour-prev").addEventListener("click", function () { tourGo(tourAt - 1); });
    $("tour-next").addEventListener("click", function () { tourGo(tourAt + 1); });
    $("tour-exit").addEventListener("click", tourExit);
    document.addEventListener("keydown", function (e) {
      if (tourAt < 0 || e.altKey || e.ctrlKey || e.metaKey) return;
      var tg = e.target && e.target.tagName;
      if (tg === "SELECT" || tg === "INPUT" || tg === "TEXTAREA" || tg === "VIDEO") return;
      if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); tourGo(tourAt + 1); }
      else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); tourGo(tourAt - 1); }
      else if (e.key === "Escape") tourExit();
    });
  }
  // ?tour=N opens the tour at step N once the clips' manifests are in
  var tourWanted = 0;
  function tourFromUrl() {
    if (!tourWanted) return;
    var n = tourWanted; tourWanted = 0; tourGo(Math.min(n, tourSteps.length) - 1);
  }

  /* ---------- footer ---------- */
  function renderFoot() {
    var f = $("foot"); clear(f);
    function A(href, text) { return el("a", { href: href, target: "_blank", rel: "noopener", text: text }); }
    function T(t) { return document.createTextNode(t); }
    f.appendChild(el("h2", { class: "credhead", text: "Method" }));
    f.appendChild(el("p", { text: "Every score comes from PlayWorld's own verifier with Gemini 3.1 Pro at the benchmark's settings. Cheaper screening judges are never shown. The judge writes its comments mostly in Chinese; English copies are machine-translated for display after scoring, never feed a score, and the judge's original text is authoritative." }));
    f.appendChild(el("p", { text: "Model-side A/Bs use fixed action scripts or the scripted player; player-side A/Bs use the AI player. Both get 4 official judge passes, and a task counts as moved only when it changes by a full point. A final score needs the AI player, all 171 tasks and 2 or more passes." }));
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

  /* ---------- watch tabs: compare player or one run's scenes ---------- */
  var mode = "compare";
  function setMode(m, user) {
    mode = m;
    [["compare", "tab-compare", "compare-clips"], ["scenes", "tab-scenes", "scenes"]].forEach(function (x) {
      var on = x[0] === m;
      $(x[1]).setAttribute("aria-selected", String(on));
      $(x[1]).setAttribute("tabindex", on ? "0" : "-1");
      $(x[2]).hidden = !on;
      if (!on) Array.prototype.forEach.call($(x[2]).querySelectorAll("video"), function (v) { if (!v.paused) v.pause(); });
    });
    if (m !== "compare" && $("cv-play").textContent === "Pause") $("cv-play").click();
    if (!user) return;
    // the other mode's deep-link params would win on reload, so drop them
    try {
      var q = new URLSearchParams(location.search);
      (m === "scenes" ? ["compare", "a", "b", "c"] : ["scenes", "scene"]).forEach(function (k) { q.delete(k); });
      var qs = q.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + "#" + (m === "scenes" ? "scenes" : "compare-clips"));
    } catch (e) { /* sandboxed */ }
    // each tab writes its own selection back to the URL
    if (m === "scenes") syncUrl(); else document.dispatchEvent(new CustomEvent("pwa:mode", { detail: m }));
  }
  function initMode() {
    var q = new URLSearchParams(location.search);
    setMode(q.has("compare") ? "compare" : (q.has("scenes") || location.hash === "#scenes") ? "scenes" : "compare", false);
    $("tab-compare").addEventListener("click", function () { setMode("compare", true); });
    $("tab-scenes").addEventListener("click", function () { setMode("scenes", true); });
    ["tab-compare", "tab-scenes"].forEach(function (id) {
      $(id).addEventListener("keydown", function (e) {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight" && e.key !== "Home" && e.key !== "End") return;
        e.preventDefault();
        var next = mode === "compare" ? "scenes" : "compare";
        if (e.key === "Home") next = "compare"; else if (e.key === "End") next = "scenes";
        setMode(next, true); $(next === "scenes" ? "tab-scenes" : "tab-compare").focus();
      });
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
        .then(function () { refreshRI(); renderScenes(); renderBoard(); renderMethods(); renderStory(); renderGlance(); document.dispatchEvent(new CustomEvent("pwa:runinfo")); tourFromUrl(); });
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
    renderStatus(); renderVerdict(); renderGlance(); renderRuler(); renderFams(); renderFull(); renderStory(); renderLoop(); renderMethods();
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
    var rz = null, lastW = window.innerWidth;
    window.addEventListener("resize", function () {
      if (window.innerWidth === lastW) return; lastW = window.innerWidth;
      clearTimeout(rz); rz = setTimeout(renderRuler, 120);
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
  initMode(); wire(); wireScenes(); wireTour(); addAnchors();
  load().then(function (o) { ALL = o.rows; source = o.s; refreshRI(); })
    .catch(function () { ALL = []; source = "unavailable: could not load the live or the bundled CSV"; })
    .then(function () { readUrl(); renderFoot(); renderAll(); loadScenes(); shareData(); });
  // hand the loaded rows and shared helpers to the Compare player (src/scripts/compare.js)
  function shareData() {
    window.PWA_SITE = { rows: ALL, getJson: getJson, famName: function (f) { return FAMINFO[f] ? FAMINFO[f].name : (f || "-"); },
      isCapped: isCapped, isScripted: isScripted, isSmoke: isSmoke, isOpen: isOpen, isClosed: isClosed, fmt: fmt,
      runInfo: function () { return RI; } };
    document.dispatchEvent(new CustomEvent("pwa:data"));
  }
})();
