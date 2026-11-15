// Client-side results page: fetches results/experiments.csv from main at view time.
"use strict";
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
  function isOpen(r) { return r.action_source === "dataset"; }
  function isClosed(r) { return r.action_source === "agent" || r.action_source === "refined"; }
  function isPartial(r) { return r.split !== "all" || (r.n_tasks !== null && r.n_tasks < FULL_TASKS); }
  // real run too small to estimate a score: fewer than a dev split of tasks, or a single verifier pass
  // capped: each rollout was cut to max_chunks agent chunks (official 30), so it is never comparable to a real score
  function isCapped(r) { return typeof r.max_chunks === "number" && r.max_chunks > 0; }
  function isSmoke(r) { return !isTest(r) && (isCapped(r) || (r.n_tasks !== null && r.n_tasks < DEV_TASKS) || (r.passes !== null && r.passes < 2)); }
  function pad2(n) { return n < 10 ? "0" + n : "" + n; }
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function fmtTime(t) {
    var d = new Date(t);
    return MON[d.getUTCMonth()] + " " + d.getUTCDate() + " " + pad2(d.getUTCHours()) + ":" + pad2(d.getUTCMinutes());
  }
  function ago(t) {
    var s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 90) return "just now";
    if (s < 5400) return Math.round(s / 60) + " min ago";
    if (s < 129600) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " days ago";
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
  var filt = { runner: "", split: "", action: "", branch: "", tests: false };
  var sort = { key: "overall", dir: -1 };
  var sel = []; // chosen experiment keys for the bar chart, in slot order
  var slotOf = {}; // exp key -> slot 1..4, stable while selected
  var touched = false;
  var cmpBase = "", cmpAuto = "";
  function key(r) { return r.exp + "@" + r.split; } // exp names are [A-Za-z0-9._-], so "@" is unambiguous and URL-friendly

  function visible() {
    return ALL.filter(function (r) {
      if (!filt.tests && isTest(r)) return false;
      if (filt.runner && r.runner !== filt.runner) return false;
      if (filt.split && r.split !== filt.split) return false;
      if (filt.action && r.action_source !== filt.action) return false;
      if (filt.branch && r.branch !== filt.branch) return false;
      return true;
    });
  }

  /* ---------- stat strip ---------- */
  function renderTiles() {
    var box = $("tiles"); clear(box);
    var nonTest = realRows(), hiddenTests = ALL.length - nonTest.length;
    var real = nonTest.filter(function (r) { return !isLive(r); });
    var closed = real.filter(isClosed).length, open = real.filter(isOpen).length;
    var finals = real.filter(isFinal).length;
    var held = real.filter(function (r) { return r.split === "heldout" || r.split === "all"; }).length;
    var last = null;
    ALL.forEach(function (r) { if (r.t !== null && (last === null || r.t > last)) last = r.t; });
    function stat(strong, rest, title) { return el("span", { class: "stat", title: title }, [el("b", { text: strong }), document.createTextNode(" " + rest)]); }
    [stat(String(real.length), "runs logged", closed + " played by the AI player, " + open + " with replayed moves" + (hiddenTests ? "; " + hiddenTests + " pipeline test" + (hiddenTests > 1 ? "s" : "") + " hidden" : "")),
     stat(finals + " of " + real.length, "meet every final-score check", finals ? "can be reported as a final score" : "none yet: the final run comes after we freeze the code"),
     stat(held ? held + " run" + (held > 1 ? "s" : "") : "Test tasks", held ? "on the 147 unseen test tasks" : "still unseen", "147 test tasks are kept unseen until the code is frozen; " + (held ? held + " logged run(s) use them" : "no logged run uses them yet")),
     stat("Updated", last === null ? "-" : ago(last), last === null ? "no timestamps" : fmtTime(last) + " UTC")
    ].forEach(function (n) { box.appendChild(n); });
  }

  /* ---------- filters ---------- */
  function fillSelect(id, values, label, cur) {
    var s = $(id); clear(s);
    s.appendChild(el("option", { value: "", text: label }));
    values.forEach(function (v) { s.appendChild(el("option", { value: v, text: v })); });
    s.value = values.indexOf(cur) >= 0 ? cur : "";
  }
  function uniq(f) {
    var seen = {}, out = [];
    ALL.forEach(function (r) { var v = f(r); if (v && !seen[v]) { seen[v] = 1; out.push(v); } });
    return out.sort();
  }
  function renderFilters() {
    fillSelect("f-runner", uniq(function (r) { return r.runner; }), "All runners", filt.runner);
    fillSelect("f-split", uniq(function (r) { return r.split; }), "All splits", filt.split);
    fillSelect("f-action", uniq(function (r) { return r.action_source; }), "All action sources", filt.action);
    fillSelect("f-branch", uniq(function (r) { return r.branch; }), "All branches", filt.branch);
    filt.branch = $("f-branch").value;
    filt.runner = $("f-runner").value; filt.split = $("f-split").value; filt.action = $("f-action").value;
    var nt = ALL.filter(isTest).length;
    $("hidden-count").textContent = nt ? "(" + nt + " hidden)" : "";
    $("f-tests").checked = filt.tests;
  }

  /* ---------- leaderboard ---------- */
  // [key, label, class, sort numeric desc first, short label for phones]
  var COLS = [
    ["exp", "Experiment", "exp", false, "Experiment"],
    ["overall", "Overall", "num", true, "All"],
    ["gc", "Geometry", "num", true, "Geo"], ["if", "Interaction", "num", true, "Int"],
    ["insight", "Insight", "num", true, "Ins"], ["outsight", "Out of sight", "num", true, "OoS"],
    ["checks", "Checks", "hide-sm", false, ""], ["n_tasks", "Tasks", "num hide-sm", true, ""],
    ["passes", "Scored", "num hide-sm", true, ""], ["t", "Run", "hide-sm", false, ""]
  ];
  function headLabel(c) {
    return c[4] && c[4] !== c[1] ? [el("span", { class: "long", text: c[1] }), el("span", { class: "short", "aria-hidden": "true", text: c[4] })] : [el("span", { text: c[1] })];
  }
  function badgesFor(r) {
    var b = el("div", { class: "badges" });
    if (r.ref) { b.appendChild(el("span", { class: "badge", text: "published, all 171 tasks" })); return b; }
    if (isLive(r)) b.appendChild(el("span", { class: "badge" + (r.status === "failed" || r.status === "cancelled" ? " warn" : ""), title: "Status row from the experiment workflow. Not a score.", text: r.status === "running" ? "running" : r.status === "generated" ? "generated, not scored" : "! " + r.status }));
    if (isTest(r)) b.appendChild(el("span", { class: "badge", title: "Produced by tests/fake_runner.py. Not a real model score.", text: "pipeline test" }));
    if (isOpen(r)) b.appendChild(el("span", { class: "badge warn", title: "The moves were replayed from the dataset instead of chosen by the AI player. Fine for quick tests, never for final scores.", text: "replayed moves, test only" }));
    else if (isClosed(r)) b.appendChild(el("span", { class: "badge ok", title: "An AI player chose every move while the world was being generated (closed loop).", text: "AI played" }));
    if (r.branch && r.branch !== "main") b.appendChild(el("span", { class: "badge warn", title: "Run from branch " + r.branch + ". The code behind this score is not merged into main yet.", text: "code not merged" }));
    if (isPartial(r)) b.appendChild(el("span", { class: "badge partial", title: "Split is not 'all' or fewer than " + FULL_TASKS + " tasks. Not comparable to the full-benchmark paper numbers.", text: "partial" }));
    if (isCapped(r)) b.appendChild(el("span", { class: "badge warn", title: "Each rollout was cut to " + r.max_chunks + " agent chunks instead of 30. A fast smoke check, never comparable to a real score.", text: "capped smoke, " + r.max_chunks + " chunks" }));
    else if (isSmoke(r)) b.appendChild(el("span", { class: "badge warn", title: "Fewer than " + DEV_TASKS + " tasks or scored only once: a quick check that the pipeline works, too small to estimate a score.", text: "tiny test run" }));
    return b;
  }
  function sortVal(r, k) {
    if (k === "checks") return r.ref ? null : checkRow(r).filter(function (v) { return v === 1; }).length;
    var v = r[k];
    return v === undefined || v === null || v === "" ? null : v;
  }
  function metaLine(r) {
    if (r.ref) return null;
    var bits = [r.runner, r.action_source, r.split, r.branch].filter(Boolean);
    var m = el("div", { class: "meta-line", text: bits.join(" · ") });
    return m;
  }
  function rowEl(r) {
    var tr = el("tr", { class: r.ref ? "ref" : "" });
    var td = el("td", { class: "exp" }, [el("div", { class: "nm", text: r.exp }), metaLine(r), badgesFor(r)]);
    if (r.notes && !r.ref) td.appendChild(el("div", { class: "meta-line notes", text: r.notes }));
    tr.appendChild(td);
    var o = el("td", { class: "num overall" });
    if (r.overall === null) dashCell(o);
    else {
      o.appendChild(el("div", { class: r.overall === BEST.overall ? "best" : "", text: fmt(r.overall) }));
      if (typeof r.overall_std === "number") o.appendChild(el("div", { class: "std", text: "±" + fmt(r.overall_std) }));
    }
    tr.appendChild(o);
    FAMS.forEach(function (f) {
      var t = el("td", { class: "num" + (r[f[0]] !== null && r[f[0]] === BEST[f[0]] ? " best" : "") }); if (r[f[0]] === null) dashCell(t); else t.textContent = fmt(r[f[0]]); tr.appendChild(t);
    });
    var ckt = el("td", { class: "hide-sm" }); if (r.ref) dashCell(ckt); else ckt.appendChild(checksEl(r)); tr.appendChild(ckt);
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
      if (r.sha && /^[0-9a-f]{7,40}$/i.test(r.sha)) tt.appendChild(el("div", null, [el("a", { href: COMMIT + r.sha, target: "_blank", rel: "noopener", text: r.sha.slice(0, 7) })]));
    }
    tr.appendChild(tt);
    return tr;
  }
  var BEST = {};
  function renderBoard() {
    var t = $("board"); clear(t);
    BEST = {};
    visible().filter(function (r) { return !isCapped(r); }).concat(REFS).forEach(function (r) {
      ["overall"].concat(FAMS.map(function (f) { return f[0]; })).forEach(function (k) {
        if (r[k] !== null && (BEST[k] === undefined || r[k] > BEST[k])) BEST[k] = r[k];
      });
    });
    var thead = el("thead"), hr = el("tr");
    COLS.forEach(function (c) {
      var th = el("th", { class: c[2], scope: "col", "aria-sort": sort.key === c[0] ? (sort.dir > 0 ? "ascending" : "descending") : "none" });
      var b = el("button", { type: "button", title: "Sort by " + c[1] }, headLabel(c).concat([el("span", { class: "arrow", "aria-hidden": "true", text: sort.key === c[0] ? (sort.dir > 0 ? "▲" : "▼") : "" })]));
      b.addEventListener("click", function () {
        if (sort.key === c[0]) sort.dir = -sort.dir; else { sort.key = c[0]; sort.dir = c[3] || c[0] === "t" ? -1 : 1; }
        renderBoard(); syncUrl();
      });
      th.appendChild(b); hr.appendChild(th);
    });
    thead.appendChild(hr); t.appendChild(thead);
    var rows = visible().slice().sort(function (a, b) {
      var x = sortVal(a, sort.key), y = sortVal(b, sort.key);
      if (x === null && y === null) return a.order - b.order;
      if (x === null) return 1; if (y === null) return -1;
      var c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return c * sort.dir || a.order - b.order;
    });
    var tb = el("tbody");
    if (!rows.length) {
      var nt = ALL.filter(isTest).length;
      var msg = ALL.length ? "No experiments match these filters." + (!filt.tests && nt ? " " + nt + " pipeline test row" + (nt > 1 ? "s are" : " is") + " hidden; tick \"Show pipeline tests\" to see them." : "")
                           : "No experiments logged yet. Run the experiment workflow and rows appear here.";
      tb.appendChild(el("tr", null, [el("td", { class: "empty", colspan: String(COLS.length), text: msg })]));
    }
    rows.forEach(function (r) { tb.appendChild(rowEl(r)); });
    t.appendChild(tb);
    var rb = el("tbody");
    rb.appendChild(el("tr", { class: "refhead" }, [el("td", { colspan: String(COLS.length), text: "Published scores from the PlayWorld paper (all 171 tasks)" })]));
    REFS.forEach(function (r) { rb.appendChild(rowEl(r)); });
    t.appendChild(rb);
  }

  /* ---------- tooltip ---------- */
  function showTip(tip, host, html, x, y) {
    clear(tip);
    html.forEach(function (n) { tip.appendChild(n); });
    tip.style.display = "block";
    var hw = host.clientWidth, tw = tip.offsetWidth, th = tip.offsetHeight;
    var lx = Math.min(Math.max(4, x + 12), hw - tw - 4);
    var ly = y - th - 10; if (ly < 4) ly = y + 14;
    tip.style.left = lx + "px"; tip.style.top = ly + "px";
  }
  function hideTip(tip) { tip.style.display = "none"; }

  function table(headers, rows) {
    var t = el("table"), h = el("tr");
    var SHORT = { "Insight": "Ins", "Out-of-sight": "OoS", "Overall": "All", "When (UTC)": "When" };
    headers.forEach(function (x, i) { h.appendChild(el("th", { class: i ? "num" : "exp" }, headLabel([0, x, 0, 0, SHORT[x] || x]))); });
    t.appendChild(el("thead", null, [h]));
    var b = el("tbody");
    rows.forEach(function (r) {
      var tr = el("tr");
      r.forEach(function (c, i) { tr.appendChild(el("td", { class: i ? "num" : "exp", text: c })); });
      b.appendChild(tr);
    });
    t.appendChild(b);
    return el("div", { class: "scroll" }, [t]);
  }

  /* ---------- bar chart ---------- */
  function slotFor(k) {
    if (slotOf[k]) return slotOf[k];
    var used = {}; sel.forEach(function (s) { if (slotOf[s]) used[slotOf[s]] = 1; });
    for (var i = 1; i <= 4; i++) if (!used[i]) { slotOf[k] = i; return i; }
    return 4;
  }
  function pruneSel(vis) {
    var keys = {}; vis.forEach(function (r) { keys[key(r)] = r; });
    sel = sel.filter(function (k) { return keys[k]; });
    Object.keys(slotOf).forEach(function (k) { if (sel.indexOf(k) < 0) delete slotOf[k]; });
    if (!touched) {
      var scored = vis.filter(function (r) { return r.overall !== null; })
        .sort(function (a, b) { return (a.t || 0) - (b.t || 0) || a.order - b.order; });
      sel = scored.slice(-3).map(key);
      slotOf = {}; sel.forEach(function (k) { slotFor(k); });
    }
  }
  function renderBarChips(vis) {
    var box = $("bar-chips"); clear(box);
    var scored = vis.filter(function (r) { return r.overall !== null; });
    if (!scored.length) { box.appendChild(el("span", { class: "std", text: "No scored experiments to chart yet. Genie 3 is shown for reference." })); return; }
    scored.forEach(function (r) {
      var k = key(r), on = sel.indexOf(k) >= 0, full = sel.length >= 4 && !on;
      var cb = el("input", { type: "checkbox" }); cb.checked = on; cb.disabled = full;
      cb.addEventListener("change", function () {
        touched = true;
        if (cb.checked) { sel.push(k); slotFor(k); } else { sel = sel.filter(function (x) { return x !== k; }); delete slotOf[k]; }
        renderBarChips(vis); renderBars(vis);
      });
      var lab = el("label", { class: full ? "off" : "", title: full ? "Up to 4 experiments at a time" : "" }, [cb]);
      lab.appendChild(el("span", { class: "sw " + (on ? "k" + slotOf[k] : ""), style: on ? null : "background:transparent" }));
      lab.appendChild(el("span", { text: r.exp }));
      box.appendChild(lab);
    });
  }
  function drawBars(series, groups) {
    var host = $("bar-svg"); clear(host);
    var W = Math.max(280, host.clientWidth || 520), H = 280;
    var m = { l: 30, r: 6, t: 10, b: 26 };
    var pw = W - m.l - m.r, ph = H - m.t - m.b;
    var maxv = 0; series.forEach(function (s) { s.vals.forEach(function (v) { if (v !== null && v > maxv) maxv = v; }); });
    var ymax = Math.max(3, Math.ceil(maxv));
    var y = function (v) { return m.t + ph - (v / ymax) * ph; };
    var svg = sv("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Grouped bar chart of per-family scores. A table view follows." });
    for (var g = 0; g <= ymax; g++) {
      svg.appendChild(sv("line", { class: g === 0 ? "baseline" : "gridline", x1: m.l, x2: W - m.r, y1: y(g), y2: y(g) }));
      svg.appendChild(sv("text", { x: m.l - 6, y: y(g) + 4, "text-anchor": "end", text: String(g) }));
    }
    var gw = pw / groups.length, n = series.length;
    var inner = gw * 0.78, gap = 2;
    var bw = Math.max(3, Math.min(30, (inner - gap * (n - 1)) / n));
    var used = bw * n + gap * (n - 1);
    var tip = $("bar-tip");
    groups.forEach(function (gr, gi) {
      var gx = m.l + gi * gw + (gw - used) / 2;
      svg.appendChild(sv("text", { x: m.l + gi * gw + gw / 2, y: H - 8, "text-anchor": "middle", text: gr[1] }));
      series.forEach(function (s, si) {
        var v = s.vals[gi], x = gx + si * (bw + gap);
        var bar = null;
        if (v !== null) {
          var top = y(v), h = y(0) - top, r = Math.min(4, bw / 2, h);
          bar = sv("path", { class: "bar " + s.cls, d: "M" + x + "," + y(0) + "V" + (top + r) + "Q" + x + "," + top + " " + (x + r) + "," + top + "H" + (x + bw - r) + "Q" + (x + bw) + "," + top + " " + (x + bw) + "," + (top + r) + "V" + y(0) + "Z" });
          svg.appendChild(bar);
        }
        var label = gr[1] + ", " + s.name + ": " + (v === null ? "no score" : fmt(v));
        var hit = sv("rect", { class: "hit", x: x - gap / 2 - 1, y: m.t, width: bw + gap + 2, height: ph, tabindex: "0", role: "img", "aria-label": label });
        var show = function (ev) {
          if (bar) bar.classList.add("hover");
          var b = hit.getBoundingClientRect(), hb = host.getBoundingClientRect(), cb = $("c-bars").getBoundingClientRect();
          var px = ev && ev.clientX !== undefined && ev.type !== "focus" ? ev.clientX : b.left + b.width / 2;
          var py = ev && ev.clientY !== undefined && ev.type !== "focus" ? ev.clientY : b.top + 20;
          var kids = [el("b", { text: v === null ? "no score" : fmt(v) }), el("div", { class: "t2", text: s.name }), el("div", { class: "t2", text: gr[1] })];
          if (v !== null && !s.isRef && GENIE[gr[0]] !== null) {
            var d = v - GENIE[gr[0]];
            kids.push(el("div", { class: "t2", text: (d >= 0 ? "+" : "-") + Math.abs(d).toFixed(2) + " vs Genie 3" }));
          }
          showTip(tip, $("c-bars"), kids, px - cb.left, py - cb.top);
        };
        var off = function () { if (bar) bar.classList.remove("hover"); hideTip(tip); };
        hit.addEventListener("pointermove", show); hit.addEventListener("pointerenter", show);
        hit.addEventListener("pointerleave", off); hit.addEventListener("focus", show); hit.addEventListener("blur", off);
        svg.appendChild(hit);
      });
    });
    host.appendChild(svg);
  }
  function renderBars(vis) {
    var groups = FAMS.concat([["overall", "Overall"]]);
    var series = [{ name: "Genie 3 (paper)", cls: "sref", isRef: true, vals: groups.map(function (g) { return GENIE[g[0]]; }) }];
    var byKey = {}; vis.forEach(function (r) { byKey[key(r)] = r; });
    sel.forEach(function (k) {
      var r = byKey[k]; if (!r) return;
      series.push({ name: r.exp, cls: "s" + slotFor(k), vals: groups.map(function (g) { return r[g[0]]; }) });
    });
    var lg = $("bar-legend"); clear(lg);
    series.forEach(function (s) {
      lg.appendChild(el("span", null, [el("span", { class: "sw " + (s.isRef ? "kref" : "k" + s.cls.slice(1)) }), el("span", { text: s.name })]));
    });
    drawBars(series, groups);
    $("bar-table").replaceChildren(table(["Experiment"].concat(groups.map(function (g) { return g[1]; })),
      series.map(function (s) { return [s.name].concat(s.vals.map(function (v) { return v === null ? "-" : fmt(v); })); })));
  }

  /* ---------- line chart ---------- */
  var runnerSlots = [];
  function runnerClass(runner) {
    var i = runnerSlots.indexOf(runner);
    return i >= 0 && i < 4 ? String(i + 1) : "other";
  }
  function drawLine(pts) {
    var host = $("line-svg"); clear(host);
    var W = Math.max(280, host.clientWidth || 520), H = 280;
    var m = { l: 34, r: 12, t: 14, b: 28 };
    var pw = W - m.l - m.r, ph = H - m.t - m.b;
    var maxv = TARGET; pts.forEach(function (p) { if (p.overall > maxv) maxv = p.overall; });
    var ymin = 1, ymax = Math.ceil((maxv + 0.2) * 2) / 2;
    var y = function (v) { return m.t + ph - ((v - ymin) / (ymax - ymin)) * ph; };
    var tmin, tmax;
    if (pts.length) {
      tmin = Math.min.apply(null, pts.map(function (p) { return p.t; })); tmax = Math.max.apply(null, pts.map(function (p) { return p.t; }));
      if (tmax - tmin < 3600000) { tmin -= 43200000; tmax += 43200000; }
      else { var padT = (tmax - tmin) * 0.06; tmin -= padT; tmax += padT; }
    } else { tmax = Date.now(); tmin = tmax - 86400000; }
    var x = function (t) { return m.l + ((t - tmin) / (tmax - tmin)) * pw; };
    var svg = sv("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Overall score of each experiment over time, with the Genie 3 target line at 2.12. A table view follows." });
    var step = ymax - ymin > 3 ? 1 : 0.5;
    for (var g = ymin; g <= ymax + 1e-9; g += step) {
      svg.appendChild(sv("line", { class: g === ymin ? "baseline" : "gridline", x1: m.l, x2: W - m.r, y1: y(g), y2: y(g) }));
      svg.appendChild(sv("text", { x: m.l - 6, y: y(g) + 4, "text-anchor": "end", text: g.toFixed(step < 1 ? 1 : 0) }));
    }
    var range = tmax - tmin, nt = W < 420 ? 3 : 5;
    for (var i = 0; i < nt; i++) {
      var tt = tmin + (range * i) / (nt - 1), d = new Date(tt);
      var lab = range < 3 * 86400000 ? MON[d.getUTCMonth()] + " " + d.getUTCDate() + " " + pad2(d.getUTCHours()) + ":" + pad2(d.getUTCMinutes()) : MON[d.getUTCMonth()] + " " + d.getUTCDate();
      svg.appendChild(sv("text", { x: x(tt), y: H - 8, "text-anchor": i === 0 ? "start" : (i === nt - 1 ? "end" : "middle"), text: lab }));
    }
    // target line
    svg.appendChild(sv("line", { x1: m.l, x2: W - m.r, y1: y(TARGET), y2: y(TARGET), stroke: "var(--ink2)", "stroke-width": 1.5, "stroke-dasharray": "6 4" }));
    svg.appendChild(sv("text", { x: m.l + 6, y: y(TARGET) - 5, "text-anchor": "start", text: "Genie 3 " + TARGET.toFixed(2) + " (paper)" }));
    // best closed-loop so far (step)
    var sorted = pts.slice().sort(function (a, b) { return a.t - b.t || a.order - b.order; });
    var best = null, path = "";
    sorted.forEach(function (p) {
      if (!isClosed(p) || isSmoke(p)) return;
      if (best === null || p.overall > best) {
        path += (path ? "H" + x(p.t) + "V" + y(p.overall) : "M" + x(p.t) + "," + y(p.overall)); best = p.overall;
      }
    });
    if (path) {
      var lastClosed = sorted.filter(function (p) { return isClosed(p) && !isSmoke(p); }).pop();
      path += "H" + (W - m.r);
      svg.appendChild(sv("path", { d: path, fill: "none", stroke: "var(--ink)", "stroke-width": 2, "stroke-linejoin": "round" }));
      void lastClosed;
    }
    var tip = $("line-tip");
    var marks = [];
    pts.forEach(function (p) {
      var cls = runnerClass(p.runner), cx = x(p.t), cy = y(p.overall);
      var c = sv("circle", { class: "k" + cls, cx: cx, cy: cy, r: 5, "stroke-width": 2, tabindex: "0", role: "img",
        fill: isOpen(p) ? "var(--surface)" : "currentColor", "aria-label": p.exp + ", overall " + fmt(p.overall) + ", " + (isOpen(p) ? "open loop" : "closed loop") });
      var show = function () {
        var cb = $("c-line").getBoundingClientRect(), b = c.getBoundingClientRect();
        showTip(tip, $("c-line"), [el("b", { text: fmt(p.overall) }), el("div", { class: "t2", text: p.exp }),
          el("div", { class: "t2", text: (p.runner || "-") + ", " + (p.action_source || "-") + ", " + (p.split || "-") }),
          el("div", { class: "t2", text: fmtTime(p.t) + " UTC" })], b.left + b.width / 2 - cb.left, b.top + 5 - cb.top);
      };
      c.addEventListener("focus", show); c.addEventListener("blur", function () { hideTip(tip); });
      marks.push({ p: p, c: c, cx: cx, cy: cy, show: show });
    });
    // nearest-point layer so the pointer only has to be close, not exact
    var layer = sv("rect", { x: m.l, y: m.t, width: pw, height: ph, fill: "transparent" });
    layer.addEventListener("pointermove", function (ev) {
      if (!marks.length) return;
      var r = svg.getBoundingClientRect(), k = W / r.width, px = (ev.clientX - r.left) * k, py = (ev.clientY - r.top) * k;
      var best2 = null, bd = 1e9;
      marks.forEach(function (mk) { var d = Math.hypot(mk.cx - px, mk.cy - py); if (d < bd) { bd = d; best2 = mk; } });
      if (best2 && bd < 40) best2.show(); else hideTip(tip);
    });
    layer.addEventListener("pointerleave", function () { hideTip(tip); });
    svg.appendChild(layer);
    marks.forEach(function (mk) { svg.appendChild(mk.c); });
    if (!pts.length) svg.appendChild(sv("text", { x: m.l + pw / 2, y: m.t + ph / 2 + 24, "text-anchor": "middle", text: "No scored experiments yet" }));
    host.appendChild(svg);
  }
  function renderLine(vis) {
    runnerSlots = []; ALL.forEach(function (r) { if (r.runner && runnerSlots.indexOf(r.runner) < 0 && !isTest(r)) runnerSlots.push(r.runner); });
    ALL.forEach(function (r) { if (r.runner && runnerSlots.indexOf(r.runner) < 0) runnerSlots.push(r.runner); });
    var pts = vis.filter(function (r) { return r.overall !== null && r.t !== null; });
    var lg = $("line-legend"); clear(lg);
    var seen = {};
    pts.forEach(function (p) {
      var c = runnerClass(p.runner), k = c + p.runner;
      if (seen[k]) return; seen[k] = 1;
      lg.appendChild(el("span", null, [el("span", { class: "sw k" + c }), el("span", { text: c === "other" ? (p.runner || "-") + " (other)" : p.runner })]));
    });
    lg.appendChild(el("span", null, [el("span", { class: "sw line", style: "border-top-color:var(--ink)" }), el("span", { text: "our best so far" })]));
    lg.appendChild(el("span", null, [el("span", { class: "sw line dash2", style: "border-top-color:var(--ink2)" }), el("span", { text: "Genie 3 target" })]));
    drawLine(pts);
    $("line-table").replaceChildren(pts.length ? table(["Experiment", "Overall", "When (UTC)", "Loop"],
      pts.slice().sort(function (a, b) { return a.t - b.t; }).map(function (p) { return [p.exp, fmt(p.overall), fmtTime(p.t), isOpen(p) ? "open" : (isClosed(p) ? "closed" : "-")]; }))
      : el("p", { class: "std", text: "No scored experiments yet." }));
  }

  /* ---------- compare ---------- */
  function thresholdFor(a, b) {
    var stds = [a.overall_std, b.overall_std].filter(function (s) { return s !== null && s !== undefined; });
    var thr = stds.length ? 2 * Math.max.apply(null, stds) : 0;
    return thr > 0 ? thr : 2 * FALLBACK_STD; // same as pwa.report.compare: a zero threshold falls back to paper variance
  }
  function renderCompare(vis) {
    var scored = vis.filter(function (r) { return r.overall !== null || FAMS.some(function (f) { return r[f[0]] !== null; }); });
    var opts = scored.map(function (r) { return [key(r), r.exp + " (" + r.split + ")", r]; })
      .concat(REFS.map(function (r) { return ["ref:" + r.exp, r.exp + " (paper)", r]; }));
    var s = $("cmp-base"); clear(s);
    opts.forEach(function (o) { s.appendChild(el("option", { value: o[0], text: o[1] })); });
    var valid = opts.some(function (o) { return o[0] === cmpBase; });
    var firstClosed = scored.filter(isClosed).sort(function (a, b) { return (a.t || 0) - (b.t || 0); })[0];
    cmpAuto = firstClosed ? key(firstClosed) : (scored[0] ? key(scored[0]) : "ref:" + GENIE.exp);
    if (!valid) cmpBase = cmpAuto;
    s.value = cmpBase;
    var base = null; opts.forEach(function (o) { if (o[0] === cmpBase) base = o[2]; });
    var t = $("cmp"); clear(t);
    var others = scored.filter(function (r) { return key(r) !== cmpBase; });
    var hr = el("tr");
    [["Experiment", "Experiment"], ["GC", "GC"], ["IF", "IF"], ["Insight", "Ins"], ["Out-of-sight", "OoS"], ["Overall", "All"]].forEach(function (h, i) {
      hr.appendChild(el("th", { class: i ? "num" : "exp", scope: "col" }, headLabel([0, h[0], 0, 0, h[1]])));
    });
    t.appendChild(el("thead", null, [hr]));
    var tb = el("tbody");
    if (!others.length) {
      tb.appendChild(el("tr", null, [el("td", { class: "empty", colspan: "6", text: scored.length ? "Only one experiment is visible. Log a second run, or choose a paper row as the baseline, to see deltas." : "No scored experiments to compare yet." })]));
    }
    others.forEach(function (r) {
      var tr = el("tr");
      var td = el("td", { class: "exp" }, [el("div", { text: r.exp }), badgesFor(r)]);
      if (base && !base.ref && base.split === "custom" && r.split === "custom") td.appendChild(el("div", { class: "badges" }, [el("span", { class: "badge warn", title: "Both are explicit task lists; the CSV does not record which tasks.", text: "! custom task sets may differ" })]));
      else if (base && !base.ref && base.split !== r.split) td.appendChild(el("div", { class: "badges" }, [el("span", { class: "badge warn", text: "! split differs from baseline" })]));
      tr.appendChild(td);
      FAMS.map(function (f) { return f[0]; }).concat(["overall"]).forEach(function (k) {
        var c = el("td", { class: "num" });
        if (r[k] === null || base[k] === null) dashCell(c);
        else {
          var d = r[k] - base[k], thr = thresholdFor(base, r), noise = Math.abs(d) < thr || d === 0;
          var box = el("div", { class: "delta" });
          var v = el("span", { class: "v " + (noise ? "" : (d > 0 ? "good" : "bad")), text: (noise ? "" : (d > 0 ? "▲ " : "▼ ")) + (d >= 0 ? "+" : "-") + Math.abs(d).toFixed(2) });
          box.appendChild(v);
          box.appendChild(el("span", { class: "badge " + (noise ? "" : (d > 0 ? "ok" : "bad")), title: "Threshold: 2x std = " + thr.toFixed(2), text: noise ? "noise" : "real" }));
          box.appendChild(el("span", { class: "abs", text: fmt(base[k]) + " → " + fmt(r[k]) }));
          c.appendChild(box);
        }
        tr.appendChild(c);
      });
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    var note = "";
    if (base && base.ref) note = "The baseline is a paper number on the full 171-task benchmark. Rows scored on a smaller split or open loop are not directly comparable.";
    $("cmp-note").textContent = note;
  }

  /* ---------- footer ---------- */
  function renderFoot() {
    var f = $("foot"); clear(f);
    function A(href, text) { return el("a", { href: href, target: "_blank", rel: "noopener", text: text }); }
    function T(t) { return document.createTextNode(t); }
    f.appendChild(el("p", { text: "Data source: " + source }));
    f.appendChild(el("p", { text: "Our rows come from results/experiments.csv in the repository, written automatically after each run. Published rows come from the PlayWorld paper and cover all 171 tasks, so only our runs on all 171 tasks compare directly with them." }));
    f.appendChild(el("p", null, [A("https://github.com/" + REPO, "Repository"), T(" | "), A("https://github.com/" + REPO + "/blob/main/results/experiments.csv", "experiments.csv")]));
    var ul = el("ul", { class: "credits", "aria-label": "Credits" });
    function li(kids) { ul.appendChild(el("li", null, kids)); }
    li([el("b", { text: "PlayWorld" }), T(" benchmark, harness, verifier and task data: Ding et al., \u201CPlayWorld: Benchmarking World Models with Agent Players over Long-Horizon Objectives\u201D, "), A("https://arxiv.org/abs/2608.13552", "arXiv:2608.13552"), T(", "), A("https://github.com/kxding/PlayWorld", "code"), T(", "), A("https://huggingface.co/datasets/jocelynd/playworld-bench", "data"), T(". Task images come from Pexels and web image search and keep their sources\u2019 terms.")]);
    li([el("b", { text: "LingBot-World v2" }), T(", Robbyant Team, \u201CInfinite Worlds with Versatile Interactions\u201D, "), A("https://arxiv.org/abs/2607.07534", "arXiv:2607.07534"), T(", "), A("https://github.com/Robbyant/lingbot-world-v2", "code"), T(", CC BY-NC-SA 4.0. Its weights and modules run unchanged at a pinned commit; "), A("https://github.com/benceruleanlu/playworld-advancement/blob/main/adapters/lingbot_world2/session.py", "our session wrapper"), T(" re-implements its causal sampling loop.")]);
    li([T("Reference scores for Genie 3 (Google DeepMind), SANA-WM (NVIDIA, "), A("https://github.com/NVlabs/Sana", "Sana"), T("), Matrix-Game 3.0 (Skywork AI, "), A("https://github.com/SkyworkAI/Matrix-Game", "Matrix-Game"), T(") and LingBot-World v2 are as reported in the PlayWorld paper.")]);
    li([T("Scoring: Gemini 3.1 Pro (Google) via the PlayWorld verifier. Agent player: OpenAI gpt-4.1-mini.")]);
    li([T("Site built with "), A("https://astro.build", "Astro"), T(".")]);
    f.appendChild(el("h2", { class: "credhead", text: "Credits" }));
    f.appendChild(ul);
  }

  /* ---------- story content (edit here as work lands) ---------- */
  var PR = "https://github.com/" + REPO + "/pull/";
  var FAMINFO = {
    gc: { name: "Geometry consistency", n: 48, q: "Does the scene keep its layout and objects as the camera moves?" },
    if: { name: "Interaction fidelity", n: 50, q: "Does each action do what the player asked, seen from the right viewpoint?" },
    insight: { name: "Insight evolution", n: 30, q: "Does something changing on screen (melting, filling, growing) keep changing?" },
    outsight: { name: "Out-of-sight evolution", n: 43, q: "When the camera looks away and back, has the hidden part of the world changed sensibly?" }
  };
  // status: shipped | testing | planned. evidence: experiment names in results/experiments.csv.
  var METHODS = [
    { title: "Base model: LingBot-World v2", status: "shipped",
      what: "Uses the open LingBot-World v2 model (1.3B and 14B sizes). Each key the player presses becomes a camera movement.", fams: ["gc", "if", "insight", "outsight"],
      body: "The strongest open model in the PlayWorld paper: 1.82 overall (scored via its web demo), and 1.95 on insight, where it beats Genie 3's 1.51. We run the released 1.3B and 14B checkpoints. The released code only takes camera poses, so we map each WASD/IJKL key to per-frame camera deltas with signs checked against upstream examples. Our first baseline on the 24 practice tasks (14B, session memory, AI player, two scorings) is 1.64 ±0.13, below the paper's 1.82. The paper scored LingBot through its web demo on all 171 tasks, so the two numbers are not like for like.",
      links: [["#14", PR + "14"]], evidence: ["lb14-session-agent-dev-v1", "lb13-stateless-gc005-v1"] },
    { title: "Persistent session memory", status: "testing",
      what: "Keeps the model's short-term memory between the player's moves, instead of starting fresh every two seconds.", fams: ["gc", "outsight"],
      body: "Upstream restarts the model for every agent step, so the world state resets every chunk. We keep the KV cache (LingBot's only memory), noise generator, camera track and VAE decoder cache alive across steps, with seamless frame stitching and a closed-loop translation normaliser. The first session run (lb14-session-agent-gc005-v1, a one-task smoke test) used the 14B model as a key check, so it is not an A/B against the 1.3B stateless baseline. The 24-task baseline (lb14-session-agent-dev-v1, 1.64) also runs with session memory. No run with session memory off exists on the same tasks and model, so its effect is unmeasured.",
      links: [["#17", PR + "17"]], evidence: [], baseline: "lb13-stateless-gc005-v1",
      // like-for-like only: same 1.3B runner as the stateless baseline
      match: function (r) { return r.runner === "lingbot_world2_1p3b" && isClosed(r) && !/stateless/i.test(r.exp + " " + r.notes); } },
    { title: "A. Insight progress scheduler", status: "planned",
      what: "Tells the model what the scene shows instead of what the player wants, so changes like melting keep going.", fams: ["insight"],
      body: "An LLM plans the stages of the process, re-prompts each chunk with the next stage, and a stall detector forces progress when frames stop changing. WAIT-only tasks run with no agent calls. In review (#32): condition LingBot on the scene caption instead of the agent goal, which is \"wait and observe\" on 29 of 30 Insight tasks. Measured so far: the baseline scores 1.58 on the 6 practice Insight tasks (paper: 1.95). All six rollouts are 30 WAIT steps with no player involved, and the judge marked three of them static in at least one scoring.", links: [["#32", PR + "32"]], evidence: [] },
    { title: "B. Control and gate fixes", status: "testing",
      what: "Optional turn fix: one turn key now turns the angle the task expects (22.5° sideways, 20° up or down) instead of 34° and 11°.", fams: ["gc", "if", "outsight"],
      body: "A failed gate (wrong viewpoint, target never leaves frame) scores 1.0 regardless of quality, so turns must land where the prompt says. Built: opt-in LingBot turn calibration, so one dataset token turns 22.5 degrees of yaw or 20 of pitch as the task prompts assume, instead of the default 34 and 11 degrees. In review (#46): opt-in re-anchoring for GC tasks, which shows the model the input image again when the commanded camera track returns to the start pose; not yet run on a GPU. In review (#59): an opt-in hint that tells the AI player how far one action turns the camera and where the commanded camera is relative to the start; unit tests only. What the 24-task baseline showed (turn calibration off): the player reversed left and right 9 to 25 times per rollout on the worst tasks, and in 4 of 6 out-of-sight rollouts the camera never returned to the start, so the judge graded no content. At the default rate one turn action is about 55 degrees, so a 90-degree turn is not a whole number of actions. Planned: pose-checked correction.",
      links: [["#23", PR + "23"], ["#46", PR + "46"], ["#59", PR + "59"]], evidence: [],
      match: function (r) { return /turn.?cal/i.test(r.exp + " " + r.notes); } },
    { title: "C. Out-of-sight state tracker", status: "planned",
      what: "Measures what the model still remembers after the camera looks away, with a look-away-and-back test.", fams: ["outsight"],
      body: "On exit, save a crop and description of the target; advance its state with an LLM while unseen; on return, condition generation on the edited anchor. In review (#37): a model of what LingBot's KV cache still holds (a 6-latent sink plus the last 8 latents, about 2 s) and a GPU probe that turns away and back to test whether recall fails exactly when the view is evicted. The analysis in issue #48 finds that 31 of the 43 out-of-sight dataset trajectories, as commanded, end at the starting view (33 with turn calibration), which stays in the pinned latents, and that the rubric caps an unchanged return at 1.0. For those tasks the question is whether the scene progresses while unseen. That count is about commanded trajectories and says nothing about where the generated camera ends up with a live player. The first planned step has run: a failure census of the 24-task baseline (issue #49). With the AI player, in 4 of 6 out-of-sight rollouts the generated camera never returned to the start view, and on the two that did return, two scorings of the same video disagreed by up to 3 points. By the rule set before the census, work on hidden-state content waits until the player and turn control are fixed.", links: [["#37", PR + "37"]], evidence: [] },
    { title: "D. Evaluation harness", status: "shipped",
      what: "Tools that run each experiment on rented GPUs, score it, log it, and publish this site.", fams: [],
      body: "pwa CLI (gen, score, report, compare, failures), sharded Modal generation, an Actions workflow that scores and logs every run to the shared CSV, and this page.",
      links: [["#16", PR + "16"], ["#18", PR + "18"], ["#28", PR + "28"]], evidence: [] }
  ];
  var STATUS_LABEL = { shipped: "in use", testing: "built, not yet tested", planned: "in review" };

  /* ---------- protocol checks ---------- */
  var CHECKS = [
    ["L", "AI chose every move", function (r) { return isClosed(r) ? 1 : 0; }],
    ["F", "all 171 tasks", function (r) { return r.split === "all" && r.n_tasks !== null && r.n_tasks >= FULL_TASKS ? 1 : 0; }],
    ["P", "scored at least twice", function (r) { return r.passes !== null && r.passes >= 2 ? 1 : 0; }],
    // all tasks scored: no missing videos and no rollouts dropped as unscored. Unknown (?) for rows logged before n_dropped existed.
    ["S", "no task left unscored", function (r) {
      if (r.n_missing !== null && r.n_missing > 0) return 0;
      if (r.n_dropped !== null && r.n_dropped > 0) return 0;
      return r.n_missing === null || r.n_dropped === null ? null : 1;
    }],
    ["C", "code merged", function (r) { return !r.branch ? null : (r.branch === "main" ? 1 : 0); }]
  ];
  function checkRow(r) { return CHECKS.map(function (c) { return c[2](r); }); }
  function isFinal(r) { return !isCapped(r) && checkRow(r).every(function (v) { return v === 1; }); }
  function checksEl(r) {
    var box = el("span", { class: "checks" }), res = checkRow(r), passed = 0;
    CHECKS.forEach(function (c, i) {
      var v = res[i]; if (v === 1) passed++;
      box.appendChild(el("span", { class: "ck " + (v === 1 ? "y" : v === 0 ? "n" : ""), title: c[1] + ": " + (v === 1 ? "yes" : v === 0 ? "no" : "unknown"), text: c[0] }));
    });
    box.setAttribute("aria-label", passed + " of " + CHECKS.length + " protocol checks pass");
    return box;
  }
  function renderCkLegend() {
    var box = $("cklegend"); clear(box);
    CHECKS.forEach(function (c) { box.appendChild(el("span", null, [el("span", { class: "ck y", text: c[0] }), el("span", { text: c[1] })])); });
    box.appendChild(el("span", null, [el("span", { class: "ck n", text: "x" }), el("span", { text: "fails" })]));
    box.appendChild(el("span", null, [el("span", { class: "ck", text: "?" }), el("span", { text: "not recorded" })]));
  }

  /* ---------- headline ---------- */
  function realRows() { return ALL.filter(function (r) { return !isTest(r); }); }
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
  function renderStatus() {
    var box = $("status"), fin = bestFinal(), bc = bestClosed(), cls = "", head, why;
    if (fin) {
      var d = fin.overall - TARGET, thr = 2 * (fin.overall_std || FALLBACK_STD);
      var real = Math.abs(d) >= thr;
      cls = d > 0 && real ? "ok" : "warn";
      head = "Final score: " + fmt(fin.overall) + (fin.overall_std !== null ? " ± " + fmt(fin.overall_std) : "") + " on all 171 tasks, " +
        (d >= 0 ? "+" : "-") + Math.abs(d).toFixed(2) + " compared with Genie 3" + (real ? "." : " (too small to count).");
      why = "Run " + fin.exp + ": the AI player chose every move, the judge scored it " + fin.passes + " times, and the code is merged.";
    } else if (bc) {
      cls = "warn";
      head = "In progress: our best score so far is " + fmt(bc.overall) + " on " + bc.n_tasks + " task" + (bc.n_tasks === 1 ? "" : "s") + ".";
      why = "It can't be compared with Genie 3's 2.12 yet. A final score needs all of these: the AI player chooses every move, all 171 tasks, the judge scores each video at least twice, no task left unscored, the code is merged, and the run happens after we freeze the code.";
    } else {
      var ns = realRows().filter(function (r) { return isClosed(r) && isSmoke(r); }).length;
      head = "In progress: no score to report yet.";
      why = (ns ? ns + " tiny test run" + (ns === 1 ? " is" : "s are") + " logged, but they are too small to estimate a score. " : "No run is logged yet. ") +
        "The first score appears after a run on all " + DEV_TASKS + " practice tasks, scored at least twice.";
    }
    // headline card: one number, one status chip, one comparison line; the protocol detail sits behind a disclosure
    var shown = fin || bc;
    box.className = "scorecard card " + cls; clear(box);
    box.appendChild(el("div", { class: "label", text: fin ? "Final score" : "Our best score" }));
    var big = el("div", { class: "big" }, [document.createTextNode(shown ? fmt(shown.overall) : "-")]);
    if (fin && fin.overall_std !== null) big.appendChild(el("span", { class: "pm", text: " ± " + fmt(fin.overall_std) }));
    box.appendChild(big);
    box.appendChild(el("div", { class: "badges" }, [fin
      ? el("span", { class: "badge " + (cls === "ok" ? "ok" : "warn"), text: "All 171 tasks" })
      : bc ? el("span", { class: "badge warn", text: "Only " + bc.n_tasks + " of " + FULL_TASKS + " tasks" })
           : el("span", { class: "badge", text: realRows().some(function (r) { return isClosed(r) && isSmoke(r); }) ? "Tiny test runs only" : "No runs yet" })]));
    var vs = "Genie 3: " + TARGET.toFixed(2) + " (paper)";
    if (fin) vs = (fin.overall - TARGET >= 0 ? "+" : "-") + Math.abs(fin.overall - TARGET).toFixed(2) + " vs Genie 3 " + TARGET.toFixed(2) + (Math.abs(fin.overall - TARGET) >= 2 * (fin.overall_std || FALLBACK_STD) ? "" : ", too small to count");
    box.appendChild(el("p", { class: "vs", text: vs }));
    var det = el("details", { class: "why" }, [el("summary", { text: fin ? "How this was measured" : "Why isn't this final yet?" }),
      el("p", null, [document.createTextNode(head + " " + why + " "), el("a", { href: "#rigor", text: "How we measure" })])]);
    box.appendChild(det);
    box.appendChild(el("p", { class: "scale", text: "Scores run 1 to 5; higher is better." }));
  }
  function renderRuler() {
    var host = $("ruler"); clear(host);
    var W = Math.max(300, host.clientWidth || 700), narrow = W < 520, H = narrow ? 160 : 132;
    var m = { l: 14, r: 14 };
    var bc = bestClosed(), fin = bestFinal(), ours = fin || bc;
    var hi = Math.max(3, ours ? Math.ceil((ours.overall + 0.3) * 2) / 2 : 3);
    var x = function (v) { return m.l + ((v - 1) / (hi - 1)) * (W - m.l - m.r); };
    var axisY = narrow ? 88 : 72;
    var svg = sv("svg", { viewBox: "0 0 " + W + " " + H, role: "img",
      "aria-label": "Overall score on a 1 to " + hi + " axis. " + REFS.map(function (r) { return r.exp + " " + fmt(r.overall); }).join(", ") +
        (ours ? ". Ours " + fmt(ours.overall) + (isFinal(ours) ? "" : " (partial)") : ". Ours: not yet scored") });
    svg.appendChild(sv("rect", { x: x(1), y: axisY - 3, width: x(TARGET) - x(1), height: 6, rx: 3, fill: "var(--wash)" }));
    svg.appendChild(sv("rect", { x: x(TARGET), y: axisY - 3, width: x(hi) - x(TARGET), height: 6, rx: 3, fill: "var(--good)", opacity: 0.18 }));
    svg.appendChild(sv("line", { x1: x(1), x2: x(hi), y1: axisY, y2: axisY, stroke: "var(--axis)" }));
    var oursX = ours ? x(ours.overall) : -1e9;
    for (var t = 1; t <= hi + 1e-9; t += 0.5) {
      svg.appendChild(sv("line", { x1: x(t), x2: x(t), y1: axisY + 4, y2: axisY + 9, stroke: "var(--axis)" }));
      if (Math.abs(x(t) - oursX) > 16) svg.appendChild(sv("text", { x: x(t), y: axisY + 22, "text-anchor": t === 1 ? "start" : (t >= hi ? "end" : "middle"), text: t.toFixed(1) }));
    }
    svg.appendChild(sv("text", { x: x(hi), y: axisY - 10, "text-anchor": "end", style: "fill:var(--good)", text: "above Genie 3" }));
    // reference markers, labels staggered on two rows above the axis
    var refs = REFS.slice().sort(function (a, b) { return a.overall - b.overall; });
    refs.forEach(function (r, i) {
      var cx = x(r.overall), ly = narrow ? axisY - 12 - i * 15 : axisY - 14 - (i % 2) * 18;
      var isG = r === GENIE;
      svg.appendChild(sv("line", { x1: cx, x2: cx, y1: ly + 3, y2: axisY - 5, stroke: isG ? "var(--ink)" : "var(--axis)", "stroke-dasharray": isG ? null : "2 2" }));
      svg.appendChild(sv("circle", { cx: cx, cy: axisY, r: isG ? 6 : 4.5, fill: isG ? "var(--ink)" : "var(--ref)" }));
      var anchor = cx < 80 ? "start" : (cx > W - 80 ? "end" : "middle");
      svg.appendChild(sv("text", { class: isG ? "lab" : "", x: cx, y: ly, "text-anchor": anchor, text: (narrow ? ({ "Matrix-Game-3.0": "MG-3.0", "LingBot-World2": "LingBot", "SANA-WM": "SANA" }[r.exp] || r.exp) : r.exp) + " " + fmt(r.overall) }));
    });
    // ours, below the axis
    if (ours) {
      var ox = x(ours.overall), partial = !isFinal(ours), oy = axisY + (narrow ? 50 : 40);
      svg.appendChild(sv("line", { x1: ox, x2: ox, y1: axisY + 6, y2: oy - 12, stroke: "var(--s1)", "stroke-width": 2 }));
      svg.appendChild(sv("circle", { cx: ox, cy: axisY, r: 7, fill: partial ? "var(--surface)" : "var(--s1)", stroke: "var(--s1)", "stroke-width": 2.5 }));
      var an = ox < 120 ? "start" : (ox > W - 120 ? "end" : "middle");
      svg.appendChild(sv("text", { class: "lab", x: ox, y: oy, "text-anchor": an, style: "fill:var(--s1)",
        text: "Ours " + fmt(ours.overall) + (partial ? " (" + ours.n_tasks + " task" + (ours.n_tasks === 1 ? "" : "s") + ", partial)" : "") }));
    }
    host.appendChild(svg);
    $("ruler-cap").textContent = "Published scores on all 171 tasks. Scores run from 1 to 5; this view shows 1 to " + hi + ". " +
      (ours ? (isFinal(ours) ? "Our marker is a final score." : "A hollow marker means our score covers only some tasks.") : "Our marker appears after our first run on all " + DEV_TASKS + " practice tasks.");
  }

  /* ---------- families ---------- */
  // one table: family, paper scores, our headline run, and our gap to Genie 3
  function renderFams() {
    var t = $("fams"); clear(t);
    var b = bestFinal() || bestClosed();
    var top = null; REFS.forEach(function (r) { if (r !== GENIE && r.exp === "LingBot-World2") top = r; });
    var oursHead = b && !isFinal(b) ? "Ours (" + b.n_tasks + " task" + (b.n_tasks === 1 ? "" : "s") + ")" : "Ours";
    var hr = el("tr");
    [["Task type", "Task type", "exp"], ["Genie 3", "G3", "num"], ["LingBot v2", "LB", "num"], [oursHead, "Ours", "num"], ["Ours vs Genie 3", "Gap", "num"]].forEach(function (h) {
      hr.appendChild(el("th", { class: h[2], scope: "col" }, headLabel([0, h[0], 0, 0, h[1]])));
    });
    t.appendChild(el("thead", null, [hr]));
    var tb = el("tbody");
    FAMS.forEach(function (f) {
      var k = f[0], info = FAMINFO[k], tr = el("tr");
      tr.appendChild(el("td", { class: "exp" }, [el("div", { class: "nm", text: info.name }), el("div", { class: "meta-line", text: info.q + " (" + info.n + " tasks)" })]));
      // underline the leader; our run competes only once it is a final score (all tasks, every check met)
      var ours = b && b[k] !== null && isFinal(b) ? b[k] : null;
      var best = Math.max(GENIE[k], top[k], ours === null ? -Infinity : ours);
      tr.appendChild(el("td", { class: "num" + (GENIE[k] === best ? " best" : ""), text: fmt(GENIE[k]) }));
      tr.appendChild(el("td", { class: "num" + (top[k] === best ? " best" : ""), text: fmt(top[k]) }));
      var o = el("td", { class: "num" + (ours !== null && ours === best ? " best" : "") });
      if (b && b[k] !== null) o.textContent = fmt(b[k]); else o.appendChild(el("span", { class: "dash", title: "No run on all practice tasks covers this task type yet; tiny test runs are not counted", text: "none yet" }));
      tr.appendChild(o);
      var g = el("td", { class: "num" });
      if (b && b[k] !== null) {
        var d = b[k] - GENIE[k];
        g.appendChild(el("span", { class: "badge " + (isFinal(b) ? (d >= 0 ? "ok" : "bad") : "partial"), title: isFinal(b) ? "" : "Partial run: not comparable to the paper's full-benchmark score", text: (d >= 0 ? "+" : "-") + Math.abs(d).toFixed(2) }));
      } else dashCell(g);
      tr.appendChild(g);
      tb.appendChild(tr);
    });
    t.appendChild(tb);
  }

  /* ---------- methods ---------- */
  function rowByExp(name) {
    var hit = null; ALL.forEach(function (r) { if (r.exp === name && (!hit || (r.t || 0) > (hit.t || 0))) hit = r; });
    return hit;
  }
  // one row per change: name, status, measured result; description and PR links open on click
  function renderMethods() {
    var box = $("methods"); clear(box);
    var order = { shipped: 0, testing: 1, planned: 2 };
    METHODS.slice().sort(function (a, b) { return order[a.status] - order[b.status]; }).forEach(function (mth) {
      var ev = mth.evidence.map(rowByExp).filter(function (r) { return r && !isLive(r); });
      if (mth.match) realRows().forEach(function (r) { if (!isLive(r) && mth.match(r) && ev.indexOf(r) < 0) ev.push(r); });
      var st = mth.status === "testing" && ev.length ? "shipped" : mth.status;
      var stText = mth.status === "testing" && ev.length ? "measured" : STATUS_LABEL[mth.status];
      var result;
      if (ev.length) result = el("span", { class: "res" }, [el("b", { text: fmt(ev[0].overall) }), document.createTextNode(" on " + ev[0].n_tasks + " task" + (ev[0].n_tasks === 1 ? "" : "s"))]);
      else if (mth.status === "planned") result = el("span", { class: "res none", text: "in review" });
      else if (!mth.fams.length) result = el("span", { class: "res none", text: "tooling" });
      else result = el("span", { class: "res none", text: mth.baseline ? "no fair comparison yet" : "not tested yet" });
      var summary = el("summary", null, [
        el("span", { class: "nm", text: mth.title.replace(/^[A-D]\. /, "") }),
        el("span", { class: "badge " + ({ shipped: "ok", testing: "warn", planned: "partial" }[st] || ""), text: stText }),
        result
      ]);
      var body = el("div", { class: "more" }, [el("p", { text: mth.what || mth.body })]);
      if (mth.what && mth.body) body.appendChild(el("p", { class: "std", text: mth.body }));
      if (ev.length) body.appendChild(el("p", { class: "std", text: "Runs: " + ev.map(function (r) { return r.exp + " (" + fmt(r.overall) + ", " + r.n_tasks + " task" + (r.n_tasks === 1 ? "" : "s") + (isClosed(r) ? "" : ", open loop") + ")"; }).join("; ") }));
      else if (mth.baseline) { var br = rowByExp(mth.baseline); body.appendChild(el("p", { class: "std", text: "Baseline logged: " + mth.baseline + (br && br.overall !== null ? " (" + fmt(br.overall) + ")" : "") + "." })); }
      var links = el("p", { class: "links" });
      mth.links.forEach(function (l) { links.appendChild(el("a", { href: l[1], target: "_blank", rel: "noopener", text: "PR " + l[0] })); });
      if (links.childNodes.length) body.appendChild(links);
      box.appendChild(el("li", null, [el("details", null, [summary, body])]));
    });
  }

  /* ---------- record progression ---------- */
  function renderRecords() {
    var t = $("records"); clear(t);
    var hr = el("tr");
    [["Experiment", "exp"], ["Overall", "num"], ["Gain", "num"], ["Verdict", ""], ["Commit", "hide-sm"]].forEach(function (h) {
      hr.appendChild(el("th", { class: h[1], scope: "col", text: h[0] }));
    });
    t.appendChild(el("thead", null, [hr]));
    var tb = el("tbody");
    var rows = realRows().filter(function (r) { return isClosed(r) && r.overall !== null && r.t !== null; })
      .sort(function (a, b) { return a.t - b.t || a.order - b.order; });
    var best = {}, recs = [];
    rows.forEach(function (r) {
      // "custom" covers any explicit --tasks list; two custom runs may score different tasks, so never compare them
      var k = r.split === "custom" ? "custom|" + r.exp : r.split + "|" + r.n_tasks, prev = best[k];
      if (!prev || r.overall > prev.overall) { recs.push([r, prev || null]); best[k] = r; }
    });
    if (!recs.length) tb.appendChild(el("tr", null, [el("td", { class: "empty", colspan: "5", text: "No closed-loop runs yet." })]));
    recs.reverse().forEach(function (p) {
      var r = p[0], prev = p[1], tr = el("tr");
      tr.appendChild(el("td", { class: "exp" }, [el("div", { class: "nm", text: r.exp }),
        el("div", { class: "meta-line", text: r.split + " split, " + r.n_tasks + " task" + (r.n_tasks === 1 ? "" : "s") + " · " + fmtTime(r.t) + " UTC" }), badgesFor(r)]));
      var o = el("td", { class: "num overall" }, [el("div", { text: fmt(r.overall) })]);
      if (r.overall_std !== null) o.appendChild(el("div", { class: "std", text: "±" + fmt(r.overall_std) }));
      tr.appendChild(o);
      var verdict, g = el("td", { class: "num" });
      if (prev) {
        var d = r.overall - prev.overall, thr = thresholdFor(prev, r), real = d >= thr;
        g.appendChild(el("div", { class: real ? "good" : "", text: "+" + d.toFixed(2) }));
        g.appendChild(el("div", { class: "std", text: "from " + fmt(prev.overall) }));
        verdict = el("span", { class: "badge " + (real ? "ok" : ""), title: "Threshold 2x std = " + thr.toFixed(2), text: real ? "real gain" : "too small to count" });
      } else {
        dashCell(g);
        verdict = el("span", { class: "badge", title: r.split === "custom" ? "Run on a hand-picked list of tasks. The log does not record which ones, so it is not compared with other runs." : "", text: r.split === "custom" ? "hand-picked tasks, not compared" : "first run on these tasks" });
      }
      tr.appendChild(g);
      tr.appendChild(el("td", null, [verdict]));
      var cm = el("td", { class: "hide-sm" });
      if (r.sha && /^[0-9a-f]{7,40}$/i.test(r.sha)) cm.appendChild(el("a", { href: COMMIT + r.sha, target: "_blank", rel: "noopener", text: r.sha.slice(0, 7) })); else dashCell(cm);
      tr.appendChild(cm);
      tb.appendChild(tr);
    });
    t.appendChild(tb);
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
  function getJson(name) {
    return get(MEDIA_RAW + name, 6000).then(JSON.parse).catch(function () { return get("media/" + name, 6000).then(JSON.parse); });
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
      el("span", { class: "sc", text: typeof t.mean === "number" ? fmt(t.mean) : (runScored(scenesMan) ? "unscored" : "no score") })
    ]);
    var row2 = el("div", { class: "row" }, [
      el("span", { class: "fam", text: famName }),
      el("span", { class: "badge " + (ok ? "ok" : "warn"), text: st.length ? st.join(", ") : "no status" })
    ]);
    var kids = [media, row, row2];
    if (t.video && /^https:/.test(t.video)) kids.push(el("div", { class: "row" }, [el("a", { class: "sclink", href: sceneLink(scenesExp, t.task_id), text: "Link to this scene" }),
      el("a", { class: "sclink", href: t.video, rel: "noopener", text: "Download mp4" })]));
    if (t.reason) kids.push(el("details", null, [el("summary", { text: "Judge's comment" }), el("p", { text: t.reason })]));
    return el("article", { class: "scene" }, kids);
  }
  function renderScenes() {
    var grid = $("sc-grid"), empty = $("sc-empty"), filt2 = $("scenes-filters");
    if (!grid) return;
    clear(grid);
    var runs = scenesIdx && scenesIdx.runs ? scenesIdx.runs : [];
    var lb = $("sc-labels"); clear(lb); lb.hidden = true;
    if (!runs.length) {
      empty.hidden = false; empty.textContent = "No scenes published yet. Each run that generates videos adds them to a GitHub Release.";
      filt2.hidden = true; $("sc-note").hidden = true; $("sc-files").hidden = true; return;
    }
    filt2.hidden = false;
    var rs = $("sc-run"), fs = $("sc-fam");
    clear(rs); runs.forEach(function (r) {
      var tags = [r.n_tasks + " tasks"];
      if (!runScored(r)) tags.push("not scored");
      if (runLabels(r).some(function (l) { return /^capped/.test(l); })) tags.push("capped");
      var o = el("option", { value: r.exp, text: r.exp + " (" + tags.join(", ") + ")" }); if (r.exp === scenesExp) o.selected = true; rs.appendChild(o);
    });
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
      empty.hidden = true; $("sc-note").hidden = !one.reason;
      grid.appendChild(sceneCard(one, true));
      var back = el("button", { class: "scmore", type: "button", text: "Show all " + tasks.length + " scenes of this run" });
      back.addEventListener("click", function () { scenesTask = ""; renderScenes(); syncUrl(); });
      grid.appendChild(el("div", { style: "grid-column:1/-1" }, [back]));
      if (!scenesScrolled) { scenesScrolled = true; var sec = $("scenes"); if (sec && sec.scrollIntoView) sec.scrollIntoView(); }
      return;
    }
    var list = tasks.filter(function (t) { return !scenesFam || t.family === scenesFam; });
    empty.hidden = list.length > 0; if (!list.length) empty.textContent = "No tasks in this family for this run.";
    $("sc-note").hidden = !list.some(function (t) { return t.reason; });
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
      return scenesExp ? loadManifest() : null;
    }).catch(function () { scenesIdx = null; }).then(function () { renderScenes(); syncUrl(); });
  }
  function wireScenes() {
    $("sc-run").addEventListener("change", function (e) {
      scenesExp = e.target.value; scenesTask = ""; scenesWanted = "";
      var req = scenesReq + 1;
      loadManifest().then(function () { if (req === scenesReq) { renderScenes(); syncUrl(); } });
    });
    $("sc-fam").addEventListener("change", function (e) { scenesFam = e.target.value; scenesAll = false; scenesTask = ""; renderScenes(); syncUrl(); });
  }

  /* ---------- render all ---------- */
  function renderAll() {
    var vis = visible();
    pruneSel(vis);
    renderStatus(); renderRuler(); renderFams(); renderMethods(); renderRecords();
    renderTiles(); renderBoard(); renderBarChips(vis); renderBars(vis); renderLine(vis); renderCompare(vis);
    syncUrl();
    var top = $("top"); if (top) top.setAttribute("aria-busy", "false");
  }
  /* ---------- shareable URL state ---------- */
  var URLKEYS = [["runner", "runner"], ["split", "split"], ["action", "action"], ["branch", "branch"]];
  function readUrl() {
    var q = new URLSearchParams(location.search);
    URLKEYS.forEach(function (k) { filt[k[1]] = q.get(k[0]) || ""; }); // unknown values are dropped by renderFilters
    filt.tests = q.get("tests") === "1";
    var sv = q.get("sort") || "", d = sv.charAt(0) === "-" ? -1 : 1, sk = sv.replace(/^-/, "");
    if (COLS.some(function (c) { return c[0] === sk; })) { sort.key = sk; sort.dir = d; }
    scenesExp = q.get("scenes") || "";
    scenesTask = scenesExp ? (q.get("scene") || "") : "";
    cmpBase = q.get("base") || ""; // unknown values fall back to the default in renderCompare
  }
  function syncUrl() {
    try {
      var q = new URLSearchParams(location.search);
      URLKEYS.forEach(function (k) { if (filt[k[1]]) q.set(k[0], filt[k[1]]); else q.delete(k[0]); });
      if (filt.tests) q.set("tests", "1"); else q.delete("tests");
      if (sort.key === "overall" && sort.dir < 0) q.delete("sort"); else q.set("sort", (sort.dir < 0 ? "-" : "") + sort.key);
      if (cmpBase && cmpBase !== cmpAuto) q.set("base", cmpBase); else q.delete("base");
      if (scenesExp && (scenesExp !== scenesDefault || scenesTask)) q.set("scenes", scenesExp); else if (scenesDefault) q.delete("scenes");
      if (scenesTask) q.set("scene", scenesTask); else if (scenesIdx) q.delete("scene");
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
        if (!(navigator.clipboard && navigator.clipboard.writeText)) return; // plain navigation
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
    $("f-runner").addEventListener("change", function (e) { filt.runner = e.target.value; renderAll(); });
    $("f-split").addEventListener("change", function (e) { filt.split = e.target.value; renderAll(); });
    $("f-action").addEventListener("change", function (e) { filt.action = e.target.value; renderAll(); });
    $("f-branch").addEventListener("change", function (e) { filt.branch = e.target.value; renderAll(); });
    $("f-tests").addEventListener("change", function (e) { filt.tests = e.target.checked; renderAll(); });
    $("charts-wrap").addEventListener("toggle", function () { if ($("charts-wrap").open) { var v = visible(); renderBars(v); renderLine(v); } });
    $("cmp-base").addEventListener("change", function (e) { cmpBase = e.target.value; renderCompare(visible()); syncUrl(); });
    var rz = null, lastW = window.innerWidth;
    window.addEventListener("resize", function () {
      if (window.innerWidth === lastW) return; lastW = window.innerWidth;
      clearTimeout(rz); rz = setTimeout(function () { var v = visible(); renderRuler(); renderBars(v); renderLine(v); }, 120);
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
  wire(); wireScenes(); addAnchors();
  load().then(function (o) { ALL = o.rows; source = o.s; })
    .catch(function () { ALL = []; source = "unavailable: could not load the live or the bundled CSV"; })
    .then(function () { readUrl(); renderFilters(); renderFoot(); renderCkLegend(); renderAll(); loadScenes(); });
})();
