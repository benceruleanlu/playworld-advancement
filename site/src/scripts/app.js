// Client-side results page: fetches results/experiments.csv from main at view time.
"use strict";
(function () {
  var REPO = "benceruleanlu/playworld-advancement";
  var RAW = "https://raw.githubusercontent.com/" + REPO + "/main/results/experiments.csv";
  var COMMIT = "https://github.com/" + REPO + "/commit/";
  var TARGET = 2.12;
  var FALLBACK_STD = Math.sqrt(0.011);
  var FULL_TASKS = 171;
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
  function isOpen(r) { return r.action_source === "dataset"; }
  function isClosed(r) { return r.action_source === "agent" || r.action_source === "refined"; }
  function isPartial(r) { return r.split !== "all" || (r.n_tasks !== null && r.n_tasks < FULL_TASKS); }
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
        n_tasks: num(o.n_tasks), n_missing: num(o.n_missing), n_dropped: num(o.n_dropped), notes: (o.notes || "").trim(), branch: (o.branch || "").trim(), order: idx
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

  /* ---------- tiles ---------- */
  function tile(label, big, note, cls, small) {
    return el("div", { class: "card tile" }, [
      el("div", { class: "label", text: label }),
      el("div", { class: "big" + (small ? " small" : "") + (cls ? " " + cls : ""), text: big }),
      el("div", { class: "note", text: note })
    ]);
  }
  function renderTiles() {
    var box = $("tiles"); clear(box);
    var real = realRows(), hiddenTests = ALL.length - real.length;
    var closed = real.filter(isClosed).length, open = real.filter(isOpen).length;
    var finals = real.filter(isFinal).length;
    box.appendChild(tile("Runs logged", String(real.length), closed + " closed loop, " + open + " open-loop A/B" + (hiddenTests ? "; " + hiddenTests + " pipeline test" + (hiddenTests > 1 ? "s" : "") + " hidden" : "")));
    box.appendChild(tile("Pass every protocol check", finals + " / " + real.length, finals ? "eligible as a final number" : "none yet: final run comes after code freeze", finals ? "good" : ""));
    var held = real.filter(function (r) { return r.split === "heldout" || r.split === "all"; }).length;
    box.appendChild(tile("Held-out split", held ? held + " run" + (held > 1 ? "s" : "") : "unused", held ? "logged on split heldout or all" : "no logged run uses split heldout or all (147 tasks)", "", true));
    var last = null;
    ALL.forEach(function (r) { if (r.t !== null && (last === null || r.t > last)) last = r.t; });
    box.appendChild(tile("Last updated", last === null ? "-" : fmtTime(last), last === null ? "no timestamps" : ago(last) + " (UTC)", "", true));
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
    ["gc", "GC", "num", true, "GC"], ["if", "IF", "num", true, "IF"],
    ["insight", "Insight", "num", true, "Ins"], ["outsight", "Out-of-sight", "num", true, "OoS"],
    ["checks", "Protocol", "hide-sm", false, ""], ["n_tasks", "Tasks", "num hide-sm", true, ""],
    ["passes", "Passes", "num hide-sm", true, ""], ["t", "Run", "hide-sm", false, ""]
  ];
  function headLabel(c) {
    return c[4] && c[4] !== c[1] ? [el("span", { class: "long", text: c[1] }), el("span", { class: "short", "aria-hidden": "true", text: c[4] })] : [el("span", { text: c[1] })];
  }
  function badgesFor(r) {
    var b = el("div", { class: "badges" });
    if (r.ref) { b.appendChild(el("span", { class: "badge", text: "paper, full benchmark" })); return b; }
    if (isTest(r)) b.appendChild(el("span", { class: "badge", title: "Produced by tests/fake_runner.py. Not a real model score.", text: "pipeline test" }));
    if (isOpen(r)) b.appendChild(el("span", { class: "badge warn", title: "action_source=dataset replays dataset actions. Valid for fast A/B only, never for final numbers.", text: "! open loop, A/B only" }));
    else if (isClosed(r)) b.appendChild(el("span", { class: "badge ok", text: "closed loop" }));
    if (r.branch && r.branch !== "main") b.appendChild(el("span", { class: "badge warn", title: "Run launched from branch " + r.branch + ", not main. The code behind this score is not merged.", text: "! unmerged code" }));
    if (isPartial(r)) b.appendChild(el("span", { class: "badge partial", title: "Split is not 'all' or fewer than " + FULL_TASKS + " tasks. Not comparable to the full-benchmark paper numbers.", text: "partial" }));
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
    visible().concat(REFS).forEach(function (r) {
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
    rb.appendChild(el("tr", { class: "refhead" }, [el("td", { colspan: String(COLS.length), text: "Reference: PlayWorld paper, full benchmark (171 tasks)" })]));
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
        var hit = sv("rect", { class: "hit", x: x - gap / 2 - 1, y: m.t, width: bw + gap + 2, height: ph, tabindex: "0", "aria-label": label });
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
      if (!isClosed(p)) return;
      if (best === null || p.overall > best) {
        path += (path ? "H" + x(p.t) + "V" + y(p.overall) : "M" + x(p.t) + "," + y(p.overall)); best = p.overall;
      }
    });
    if (path) {
      var lastClosed = sorted.filter(isClosed).pop();
      path += "H" + (W - m.r);
      svg.appendChild(sv("path", { d: path, fill: "none", stroke: "var(--ink)", "stroke-width": 2, "stroke-linejoin": "round" }));
      void lastClosed;
    }
    var tip = $("line-tip");
    var marks = [];
    pts.forEach(function (p) {
      var cls = runnerClass(p.runner), cx = x(p.t), cy = y(p.overall);
      var c = sv("circle", { class: "k" + cls, cx: cx, cy: cy, r: 5, "stroke-width": 2, tabindex: "0",
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
    lg.appendChild(el("span", null, [el("span", { class: "sw line", style: "border-top-color:var(--ink)" }), el("span", { text: "best closed-loop so far" })]));
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
    f.appendChild(el("p", { text: "Data source: " + source }));
    f.appendChild(el("p", { text: "Rows: results/experiments.csv in the repo, written by pwa report. Paper rows are from the PlayWorld paper (full benchmark, 171 tasks). Our rows use the split shown, so only split=all closed-loop rows are comparable to them." }));
    f.appendChild(el("p", null, [el("a", { href: "https://github.com/" + REPO, target: "_blank", rel: "noopener", text: "Repository" }),
      document.createTextNode(" | "), el("a", { href: "https://github.com/" + REPO + "/blob/main/results/experiments.csv", target: "_blank", rel: "noopener", text: "experiments.csv" })]));
  }

  /* ---------- story content (edit here as work lands) ---------- */
  var PR = "https://github.com/" + REPO + "/pull/";
  var FAMINFO = {
    gc: { name: "Geometry consistency", n: 48, q: "Does the scene keep its layout and objects as the camera moves?" },
    if: { name: "Interaction fidelity", n: 50, q: "Do actions do what the agent asked, from the right viewpoint?" },
    insight: { name: "Insight evolution", n: 30, q: "Does a process in view (melting, filling, growing) actually progress?" },
    outsight: { name: "Out-of-sight evolution", n: 43, q: "When the camera looks away and back, has the hidden world moved on plausibly?" }
  };
  var TARGETED = { insight: 1, outsight: 1 };
  // status: shipped | testing | planned. evidence: experiment names in results/experiments.csv.
  var METHODS = [
    { title: "Base model: LingBot-World v2", status: "shipped", fams: ["gc", "if", "insight", "outsight"],
      body: "The strongest open model in the PlayWorld paper: 1.82 overall (scored via its web demo), and 1.95 on insight, where it beats Genie 3's 1.51. We run the released 1.3B and 14B checkpoints. The released code only takes camera poses, so we map each WASD/IJKL key to per-frame camera deltas with signs checked against upstream examples.",
      links: [["#14", PR + "14"]], evidence: ["lb13-stateless-gc005-v1"] },
    { title: "Persistent session memory", status: "testing", fams: ["gc", "outsight"],
      body: "Upstream restarts the model for every agent step, so the world forgets itself every chunk. We keep the KV cache (LingBot's only memory), noise generator, camera track and VAE decoder cache alive across steps, with seamless frame stitching and a closed-loop translation normaliser.",
      links: [["#17", PR + "17"]], evidence: [], baseline: "lb13-stateless-gc005-v1",
      match: function (r) { return /^lingbot/.test(r.runner) && isClosed(r) && !/stateless/i.test(r.exp + " " + r.notes); } },
    { title: "A. Insight progress scheduler", status: "planned", fams: ["insight"],
      body: "An LLM plans the stages of the process, re-prompts each chunk with the next stage, and a stall detector forces progress when frames stop changing. WAIT-only tasks run with no agent calls.", links: [], evidence: [] },
    { title: "B. Control and gate fixes", status: "planned", fams: ["gc", "if", "outsight"],
      body: "Calibrate action magnitudes and check the resulting pose, because a failed gate (wrong viewpoint, target never leaves frame) scores 1.0 regardless of quality. Re-inject the first frame when the pose returns near start.", links: [], evidence: [] },
    { title: "C. Out-of-sight state tracker", status: "planned", fams: ["outsight"],
      body: "On exit, save a crop and description of the target; advance its state with an LLM while unseen; on return, condition generation on the edited anchor.", links: [], evidence: [] },
    { title: "D. Evaluation harness", status: "shipped", fams: [],
      body: "pwa CLI (gen, score, report, compare, failures), sharded Modal generation, an Actions workflow that scores and logs every run to the shared CSV, and this page.",
      links: [["#16", PR + "16"]], evidence: [] }
  ];
  var STATUS_LABEL = { shipped: "shipped", testing: "built, A/B pending", planned: "planned" };

  /* ---------- protocol checks ---------- */
  var CHECKS = [
    ["L", "closed loop", function (r) { return isClosed(r) ? 1 : 0; }],
    ["F", "full 171 tasks", function (r) { return r.split === "all" && r.n_tasks !== null && r.n_tasks >= FULL_TASKS ? 1 : 0; }],
    ["P", "2+ verifier passes", function (r) { return r.passes !== null && r.passes >= 2 ? 1 : 0; }],
    // all tasks scored: no missing videos and no rollouts dropped as unscored. Unknown (?) for rows logged before n_dropped existed.
    ["S", "every task scored", function (r) {
      if (r.n_missing !== null && r.n_missing > 0) return 0;
      if (r.n_dropped !== null && r.n_dropped > 0) return 0;
      return r.n_missing === null || r.n_dropped === null ? null : 1;
    }],
    ["C", "code on main", function (r) { return !r.branch ? null : (r.branch === "main" ? 1 : 0); }]
  ];
  function checkRow(r) { return CHECKS.map(function (c) { return c[2](r); }); }
  function isFinal(r) { return checkRow(r).every(function (v) { return v === 1; }); }
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
    realRows().forEach(function (r) { if (isClosed(r) && r.overall !== null && (!best || r.overall > best.overall)) best = r; });
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
      head = "Final: " + fmt(fin.overall) + (fin.overall_std !== null ? " ± " + fmt(fin.overall_std) : "") + " on all 171 tasks, " +
        (d >= 0 ? "+" : "-") + Math.abs(d).toFixed(2) + " vs Genie 3" + (real ? "." : " (within noise).");
      why = fin.exp + ", closed loop, " + fin.passes + " verifier passes, code on main.";
    } else if (bc) {
      cls = "warn";
      head = "In progress: best closed-loop score so far is " + fmt(bc.overall) + " on " + bc.n_tasks + " task" + (bc.n_tasks === 1 ? "" : "s") + ".";
      why = "Not yet comparable to Genie 3's 2.12. A final number must pass every protocol check: closed loop, all 171 tasks, 2+ verifier passes, every task scored, code on main, run after code freeze.";
    } else {
      head = "In progress: no closed-loop score logged yet.";
      why = "Rows appear here as soon as the experiment workflow finishes a run.";
    }
    box.className = "status " + cls; clear(box);
    box.appendChild(el("span", { class: "dot", "aria-hidden": "true" }));
    box.appendChild(el("div", null, [el("p", null, [el("b", { text: head })]), el("p", { class: "why", text: why })]));
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
    svg.appendChild(sv("text", { x: x(hi), y: axisY - 10, "text-anchor": "end", style: "fill:var(--good)", text: "beats Genie 3 →" }));
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
    $("ruler-cap").textContent = "Reference scores are the PlayWorld paper's full-benchmark numbers. " +
      (ours ? (isFinal(ours) ? "Ours is the best run passing every protocol check." : "Ours is the best closed-loop run so far; the hollow marker means it is not yet a full-benchmark result.")
            : "Our marker appears after the first closed-loop run.") + " Axis is zoomed to 1-" + hi + " of the 1-5 scale.";
  }

  /* ---------- families ---------- */
  function renderFams() {
    var box = $("fams"); clear(box);
    var scaleMax = 3;
    FAMS.forEach(function (f) {
      var k = f[0], info = FAMINFO[k], b = bestFinal() || bestClosed();
      var top = null; REFS.forEach(function (r) { if (r !== GENIE && (!top || r[k] > top[k])) top = r; });
      var rows = [[ "Genie 3", GENIE[k], "ref" ], [ top.exp.replace("-World2", " v2"), top[k], "ref" ]];
      var card = el("div", { class: "card fam" }, [
        el("div", { class: "head" }, [el("h3", { text: info.name }), el("span", { class: "n", text: info.n + " tasks" })]),
        el("p", { class: "q", text: info.q })
      ]);
      var bars = el("div", { class: "bars" });
      function bar(name, v, cls, title) {
        var w = v === null ? 0 : Math.max(0, Math.min(1, (v - 1) / (scaleMax - 1))) * 100;
        // no fill element at all when there is no score, so an empty track never shows a sliver
        var tr = el("div", { class: "track" }, v === null || w <= 0 ? [] : [el("div", { class: "fill " + cls, style: "width:" + w.toFixed(1) + "%" })]);
        bars.appendChild(el("div", { class: "row", title: title || "" }, [el("span", { class: "nm", text: name }), tr,
          el("span", { class: "v" + (v === null ? " none" : ""), text: v === null ? "not run" : fmt(v) })]));
      }
      rows.forEach(function (r) { bar(r[0], r[1], r[2]); });
      var oursName = b && !isFinal(b) ? "Ours (" + b.n_tasks + " task" + (b.n_tasks === 1 ? "" : "s") + ")" : "Ours";
      if (b) bar(oursName, b[k], "ours" + (isFinal(b) ? "" : " partial"), b.exp + (b[k] === null ? ": no tasks from this family" : ""));
      else bar("Ours", null, "ours", "no closed-loop score yet");
      card.appendChild(bars);
      var gap = GENIE[k] - 1;
      card.appendChild(el("div", { class: "foot" }, [
        el("span", { class: "badge " + (TARGETED[k] ? "accent" : ""), text: TARGETED[k] ? "Primary target" : "Hold the line" }),
        el("span", { class: "note", text: TARGETED[k] ? "Genie 3 is only " + fmt(gap) + " above the 1.0 floor." : "Genie 3 leads at " + fmt(GENIE[k]) + "." })
      ]));
      box.appendChild(card);
    });
  }

  /* ---------- methods ---------- */
  function rowByExp(name) {
    var hit = null; ALL.forEach(function (r) { if (r.exp === name && (!hit || (r.t || 0) > (hit.t || 0))) hit = r; });
    return hit;
  }
  function renderMethods() {
    var box = $("methods"); clear(box);
    METHODS.forEach(function (mth) {
      var ev = mth.evidence.map(rowByExp).filter(Boolean);
      if (mth.match) realRows().forEach(function (r) { if (mth.match(r) && ev.indexOf(r) < 0) ev.push(r); });
      var stKey = mth.status === "testing" && ev.length ? "shipped" : mth.status;
      var stText = mth.status === "testing" && ev.length ? "A/B runs logged" : STATUS_LABEL[mth.status];
      var card = el("div", { class: "card method" }, [
        el("div", { class: "top" }, [el("h3", { text: mth.title }), el("span", { class: "badge " + ({ shipped: "ok", testing: "warn", planned: "partial" }[stKey] || ""), text: stText })]),
        el("p", { text: mth.body })
      ]);
      if (ev.length || mth.baseline) {
        var ul = el("ul");
        ev.forEach(function (r) {
          ul.appendChild(el("li", { text: r.exp + ": " + (r.overall === null ? "unscored" : fmt(r.overall)) + " overall, " + r.n_tasks + " task" + (r.n_tasks === 1 ? "" : "s") + ", " + (isClosed(r) ? "closed loop" : "open loop") }));
        });
        if (mth.baseline && !ev.length) {
          var br = rowByExp(mth.baseline);
          ul.appendChild(el("li", { text: "A/B baseline logged: " + mth.baseline + (br && br.overall !== null ? " (" + fmt(br.overall) + ")" : "") + ". Session run pending." }));
        }
        card.appendChild(el("div", { class: "ev" }, [el("b", { text: "Evidence" }), ul]));
      }
      var meta = el("div", { class: "meta" });
      if (mth.fams.length) meta.appendChild(el("span", { text: "Targets: " + mth.fams.map(function (k) { return FAMINFO[k].name.split(" ")[0]; }).join(", ") }));
      mth.links.forEach(function (l) { meta.appendChild(el("a", { href: l[1], target: "_blank", rel: "noopener", text: "PR " + l[0] })); });
      if (meta.childNodes.length) card.appendChild(meta);
      box.appendChild(card);
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
        verdict = el("span", { class: "badge " + (real ? "ok" : ""), title: "Threshold 2x std = " + thr.toFixed(2), text: real ? "real gain" : "within noise" });
      } else {
        dashCell(g);
        verdict = el("span", { class: "badge", title: r.split === "custom" ? "Explicit task list; the CSV does not record which tasks, so it is not compared with other runs." : "", text: r.split === "custom" ? "custom tasks, not compared" : "first on split" });
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

  /* ---------- render all ---------- */
  function renderAll() {
    var vis = visible();
    pruneSel(vis);
    renderStatus(); renderRuler(); renderFams(); renderMethods(); renderRecords();
    renderTiles(); renderBoard(); renderBarChips(vis); renderBars(vis); renderLine(vis); renderCompare(vis);
    syncUrl();
  }
  /* ---------- shareable URL state ---------- */
  var URLKEYS = [["runner", "runner"], ["split", "split"], ["action", "action"], ["branch", "branch"]];
  function readUrl() {
    var q = new URLSearchParams(location.search);
    URLKEYS.forEach(function (k) { filt[k[1]] = q.get(k[0]) || ""; }); // unknown values are dropped by renderFilters
    filt.tests = q.get("tests") === "1";
    var sv = q.get("sort") || "", d = sv.charAt(0) === "-" ? -1 : 1, sk = sv.replace(/^-/, "");
    if (COLS.some(function (c) { return c[0] === sk; })) { sort.key = sk; sort.dir = d; }
    cmpBase = q.get("base") || ""; // unknown values fall back to the default in renderCompare
  }
  function syncUrl() {
    try {
      var q = new URLSearchParams(location.search);
      URLKEYS.forEach(function (k) { if (filt[k[1]]) q.set(k[0], filt[k[1]]); else q.delete(k[0]); });
      if (filt.tests) q.set("tests", "1"); else q.delete("tests");
      if (sort.key === "overall" && sort.dir < 0) q.delete("sort"); else q.set("sort", (sort.dir < 0 ? "-" : "") + sort.key);
      if (cmpBase && cmpBase !== cmpAuto) q.set("base", cmpBase); else q.delete("base");
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
  wire(); addAnchors();
  load().then(function (o) { ALL = o.rows; source = o.s; })
    .catch(function () { ALL = []; source = "unavailable: could not load the live or the bundled CSV"; })
    .then(function () { readUrl(); renderFilters(); renderFoot(); renderCkLegend(); renderAll(); });
})();
