// The Pairs section: pick a comparison, filter by family and seed, step through its control/treatment pairs.
// Pairs come from pairs.js; compare.js plays the open pair (pwa:compare) or the hand-picked runs (pwa:hand).
// URL: ?cmp=KEY&fam=&seed=&pair=TASK#pairs. Old ?compare=TASK&b=C&c=T links open the derived pair when there
// is one, otherwise hand-pick mode with a note. No scores are computed or compared here.
import * as RunInfo from "./runinfo.js";
import { derivePairs, findComparison, filterPairs, seedsOf, pairId, pairById, readState, writeState, mapLegacy, SECTIONS } from "./pairs.js";
import { $, el, clear, segmented } from "./ui.js";
(function () {
  var FAM = { gc: "GC", if: "IF", insight: "Insight", outsight: "Out-of-sight" };
  var FAM_ORDER = ["gc", "if", "insight", "outsight"];
  var api = null, D = null, RI = null, mans = {};
  var st = { cmp: "", fam: "", seed: "", pair: "" };
  var cur = null, list = [], idx = -1, hand = false, open = true, playing = false;

  function famName(f) { return FAM[f] || f || "-"; }
  function narrow() { return !!(window.matchMedia && window.matchMedia("(max-width: 599px)").matches); }
  function lazy() { return !!(window.matchMedia && window.matchMedia("(max-width: 899px)").matches) || !!(navigator.connection && navigator.connection.saveData); }
  function clip(exp, task) { var m = mans[exp]; return m ? (m.tasks || []).filter(function (t) { return t.task_id === task; })[0] || null : null; }
  function seedText(s) { return s.indexOf("/") > 0 ? "seeds " + s.replace("/", " and ") : "seed " + s; }

  /* ---------- load ---------- */
  function start() {
    if (api || !window.PWA_SITE) return;
    api = window.PWA_SITE;
    api.getJson("index.json").then(function (ix) {
      var runs = (ix && ix.runs) || [];
      return Promise.all(runs.map(function (r) {
        return api.getJson(r.exp + ".json").then(function (m) { if (m && m.exp === r.exp) mans[r.exp] = m; }, function () {});
      })).then(function () { return ix; });
    }).then(function (ix) {
      RI = RunInfo.build(api.rows, (ix && ix.runs) || [], mans);
      D = derivePairs(ix, mans, RI, { origin: location.origin });
      ready();
    }, function () { D = { comparisons: [], repeats: [], byTriple: {}, runs: [] }; ready(); });
  }
  function ready() {
    headerLine();
    var q = new URLSearchParams(location.search);
    var all = D.comparisons.concat(D.repeats);
    if (!all.length) { $("pr-cmp").replaceChildren(el("option", { text: "No published clip pairs yet" })); $("pr-cmp").disabled = true; return; }
    fillPicker(); chips();
    if (q.has("compare")) {
      var task = q.get("compare") || "", m = q.get("a") ? null : mapLegacy(D, task, q.get("b") || "", q.get("c") || "");
      if (m) { selectPair(m.cmp, m.task, m.ctl, m.trt, false); landOn("compare-clips"); return; }
      st = readState(location.search); cur = findComparison(D, st.cmp) || D.comparisons[0]; st.cmp = cur.key; refilter();
      toHand({ fromUrl: true, note: q.get("a") ? "" : "Not a derived control/treatment pair: different seed or flags." });
      render();
      return;
    }
    st = readState(location.search);
    cur = findComparison(D, st.cmp) || D.comparisons[0] || D.repeats[0];
    st.cmp = cur.key;
    if (FAM_ORDER.indexOf(st.fam) < 0) st.fam = "";
    if (seedsOf(cur).indexOf(st.seed) < 0) st.seed = "";
    refilter();
    idx = Math.max(0, pairById(list, st.pair));
    render(); openCurrent(false);
    if (st.pair || location.hash === "#pairs") landOn(st.pair ? "pr-nav" : "pairs");
  }
  // the page moved while the clips loaded: put a deep-linked target back at the top
  function landOn(id) { setTimeout(function () { var n = $(id); if (n && n.scrollIntoView) n.scrollIntoView({ block: "start" }); }, 0); }
  function headerLine() {
    var line = $("pairs-line"); if (!line) return;
    var n = 0, runs = {};
    D.comparisons.forEach(function (c) { n += c.pairs.length; c.pairs.forEach(function (p) { runs[p.ctl] = 1; runs[p.trt] = 1; }); });
    if (!n) return;
    line.textContent = n + " control/treatment pairs from " + Object.keys(runs).length + " runs. Same task, same seed, same fixed actions unless the AI player drove.";
    line.hidden = false;
  }

  /* ---------- state ---------- */
  function refilter() {
    list = filterPairs(cur, st.fam, st.seed);
    if (!list.length && st.fam) { st.fam = ""; list = filterPairs(cur, "", st.seed); }
    if (!list.length && st.seed) { st.seed = ""; list = filterPairs(cur, st.fam, ""); }
  }
  function syncUrl() {
    if (hand) return;
    st.pair = idx >= 0 && list[idx] ? pairId(list, list[idx]) : "";
    try { var qs = writeState(location.search, st); history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + "#pairs"); } catch (e) { /* sandboxed */ }
  }
  function pickComparison(key, keepFilters) {
    var c = findComparison(D, key); if (!c) return;
    cur = c; st.cmp = c.key;
    if (!keepFilters) { st.fam = ""; st.seed = ""; }
    refilter(); idx = 0; leaveHand();
    render(); openCurrent(false); syncUrl();
  }
  // a known triple: its comparison, filters cleared, that pair open
  function selectPair(key, task, ctl, trt, play) {
    cur = findComparison(D, key); st.cmp = key; st.fam = ""; st.seed = "";
    refilter();
    idx = 0;
    list.forEach(function (p, i) { if (p.task === task && p.ctl === ctl && p.trt === trt) idx = i; });
    leaveHand(); render(); openCurrent(play); syncUrl();
  }
  function go(n, play) {
    if (!list.length) return;
    var j = idx + n;
    if (j < 0 || j >= list.length) return false;
    idx = j; open = true;
    render(); openCurrent(play); syncUrl();
    return true;
  }
  function toHand(d) {
    hand = true; $("pr-handbar").hidden = false; $("pr-nav").hidden = true; $("cv-pick").hidden = false;
    $("compare-clips").hidden = false; $("pr-sticky").hidden = true;
    document.dispatchEvent(new CustomEvent("pwa:hand", { detail: d || {} }));
  }
  function leaveHand() {
    if (!hand) return;
    hand = false; $("pr-handbar").hidden = true; // syncUrl drops ?compare=, a, b, c
  }

  /* ---------- render ---------- */
  function shortLabel(c) {
    if (c.repeat) return "Seed repeat · " + (c.base.length ? c.base.length + " flags" : "no flags");
    var add = c.added.length > 2 ? c.added.slice(0, 2).join(", ") + " +" + (c.added.length - 2) : c.added.join(", ");
    var base = !c.base.length ? "no flags" : c.base.length <= 2 ? c.base.join(", ") : c.base.length + " flags";
    return "+ " + add + " · on " + base + (c.section === "agent" ? " · AI player" : c.section === "scripted" ? " · scripted" : c.capped ? " · capped" : "");
  }
  function fillPicker() {
    var sx = $("pr-cmp"); clear(sx); sx.disabled = false;
    SECTIONS.forEach(function (s) {
      var cs = (s[0] === "repeats" ? D.repeats : D.comparisons.filter(function (c) { return c.section === s[0]; }));
      if (!cs.length) return;
      var og = el("optgroup", { label: s[1] });
      cs.forEach(function (c) { og.appendChild(el("option", { value: c.key, text: c.label + " · " + c.pairs.length + (c.pairs.length === 1 ? " pair" : " pairs") })); });
      sx.appendChild(og);
    });
  }
  function chips() {
    var box = $("pr-chips"); clear(box);
    D.comparisons.slice(0, 6).forEach(function (c) {
      var b = el("button", { type: "button", class: "prchip", "data-key": c.key, title: c.label, "aria-pressed": "false" }, [el("span", { class: "prchip-t", text: shortLabel(c) }), el("span", { class: "prchip-n", text: String(c.pairs.length) })]);
      b.addEventListener("click", function () { pickComparison(c.key); });
      box.appendChild(b);
    });
  }
  function bothLine(p) {
    var c = RI.get(p.ctl);
    var parts = [c ? c.size : "", c ? c.driver : "", cur.base.length ? cur.base.join(", ") : "no other flags", seedText(p.seed)];
    var pm = mans[p.ctl] && mans[p.ctl].player_model; if (pm) parts.push("player " + pm);
    return "Both arms: " + parts.filter(Boolean).join(", ") + ".";
  }
  function render() {
    $("pr-cmp").value = cur.key;
    Array.prototype.forEach.call(document.querySelectorAll("#pr-chips .prchip"), function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-key") === cur.key)); });
    // filters: family with counts, seed only when this comparison has both
    $("pr-filters").hidden = false;
    var fam = $("pr-fam"); clear(fam);
    var base = filterPairs(cur, "", st.seed), counts = {};
    base.forEach(function (p) { counts[p.family] = (counts[p.family] || 0) + 1; });
    var items = [["", "All " + base.length]].concat(FAM_ORDER.filter(function (f) { return counts[f]; }).map(function (f) { return [f, famName(f) + " " + counts[f]]; }));
    fam.appendChild(segmented("Family", items, st.fam, function (v, kb) { st.fam = v; refilter(); idx = 0; render(); openCurrent(false); syncUrl(); if (kb) focusSeg("pr-fam"); }));
    var seeds = seedsOf(cur), sd = $("pr-seed"); clear(sd);
    sd.hidden = seeds.length < 2;
    if (seeds.length > 1) sd.appendChild(segmented("Seed", [["", "All seeds"]].concat(seeds.map(function (s) { return [s, "Seed " + s]; })), st.seed,
      function (v, kb) { st.seed = v; refilter(); idx = 0; render(); openCurrent(false); syncUrl(); if (kb) focusSeg("pr-seed"); }));
    var p = list[idx];
    // what differs, and what both arms share
    var df = $("pr-diff"); clear(df);
    if (p) {
      df.appendChild(document.createTextNode(cur.repeat ? "Only difference: the seed (" + p.seed.replace("/", " vs ") + "). Same flags in both runs." : RunInfo.difference(RI.get(p.ctl), RI.get(p.trt))));
      df.appendChild(el("span", { class: "cvboth", text: bothLine(p) }));
    }
    df.hidden = !p;
    var nb = $("pr-notes"); clear(nb);
    var notes = [];
    if (cur.section === "agent") notes.push(["warn", "AI player chose moves in each arm: actions differ, so the clips are not the same path."]);
    if (cur.section === "scripted") notes.push(["warn", "Scripted player: the dataset moves replayed chunk by chunk, no AI player."]);
    if (cur.capped) notes.push(["warn", "Capped smoke runs: each rollout stopped early."]);
    if (cur.repeat) notes.push(["", "Same flags, seed 0 vs seed 1 (no method difference). Shows how much the seed alone changes a clip."]);
    if (p && p.cross) notes.push(["", "Control from another run: " + p.ctl + "."]);
    if (p && p.shaDiff) notes.push(["warn", "Different code version: " + shaOf(p.ctl) + " vs " + shaOf(p.trt) + "."]);
    notes.forEach(function (n) { nb.appendChild(el("span", { class: "badge" + (n[0] ? " " + n[0] : ""), text: n[1] })); });
    nb.hidden = !notes.length;
    // position
    $("pr-nav").hidden = hand || !p;
    if (p) $("pr-pos").textContent = "Pair " + (idx + 1) + " of " + list.length + " · " + p.task + " · " + famName(p.family) + " · " + seedText(p.seed);
    $("pr-prev").disabled = idx <= 0; $("pr-next").disabled = idx >= list.length - 1;
    $("prs-prev").disabled = idx <= 0; $("prs-next").disabled = idx >= list.length - 1;
    $("prs-count").textContent = p ? (idx + 1) + " / " + list.length : "";
    $("pr-sticky").hidden = hand || !p || !open;
    $("compare-clips").hidden = !hand && !open;
    grid();
    preloadNext();
  }
  function shaOf(exp) { var s = mans[exp] && mans[exp].git_sha; return s ? s.slice(0, 7) : "not recorded"; }
  function focusSeg(id) { var b = document.querySelector("#" + id + ' [aria-selected="true"]'); if (b) b.focus(); }
  function poster(exp, task, role) {
    var t = clip(exp, task);
    var img = t && t.poster ? el("img", { src: t.poster, alt: "", loading: "lazy", decoding: "async", width: "320", height: "180" }) : el("span", { class: "prnoposter", text: "no poster" });
    return el("figure", { class: "prposter" }, [img, el("figcaption", { text: role })]);
  }
  var gridKey = "";
  function grid() {
    var g = $("pair-grid"), key = cur.key + "|" + st.fam + "|" + st.seed;
    $("pr-gridh").hidden = !list.length;
    $("pr-gridh").textContent = "All " + list.length + (list.length === 1 ? " pair" : " pairs") + " in this comparison";
    if (key !== gridKey) {
      gridKey = key; clear(g);
      list.forEach(function (p, i) {
        var badges = el("span", { class: "badges" }, [el("span", { class: "badge", text: seedText(p.seed) })]);
        if (p.cross) badges.appendChild(el("span", { class: "badge", text: "control from " + p.ctl }));
        if (p.shaDiff) badges.appendChild(el("span", { class: "badge warn", text: "different code version" }));
        var b = el("button", { type: "button", class: "prcard", "data-i": String(i), "aria-label": "Open pair " + (i + 1) + ": " + p.task + ", " + famName(p.family) + ", " + seedText(p.seed) }, [
          el("span", { class: "prposters" }, [poster(p.ctl, p.task, "Control"), poster(p.trt, p.task, "Treatment")]),
          el("span", { class: "prmeta" }, [el("b", { text: p.task }), el("span", { text: famName(p.family) })]),
          badges
        ]);
        b.addEventListener("click", function () { idx = i; open = true; render(); openCurrent(false); syncUrl(); scrollToPlayer(); });
        g.appendChild(b);
      });
    }
    Array.prototype.forEach.call(g.children, function (c, i) { c.setAttribute("aria-current", i === idx && !hand ? "true" : "false"); });
  }
  // desktop only: the next pair's posters, never its video
  function preloadNext() {
    if (lazy() || !list[idx + 1]) return;
    var p = list[idx + 1];
    [p.ctl, p.trt].forEach(function (e) { var t = clip(e, p.task); if (t && t.poster) { var im = new Image(); im.src = t.poster; } });
  }
  function heads(p) {
    if (cur.repeat) return [seedText(p.seed.split("/")[0]), seedText(p.seed.split("/")[1])];
    var add = cur.added.join(", ");
    return ["without " + add, "+ " + add];
  }
  function openCurrent(play) {
    var p = list[idx]; if (!p || hand) return;
    // phones never start a clip without a tap
    document.dispatchEvent(new CustomEvent("pwa:compare", { detail: { task: p.task, b: p.ctl, c: p.trt, play: !!play, heads: heads(p), cross: p.cross ? p.ctl : "", pair: true } }));
  }
  function scrollToPlayer() {
    var n = $("pr-nav"); if (!n || !n.scrollIntoView) return;
    var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    n.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
  }
  function closePlayer() {
    if (playing) $("cv-play").click();
    open = false; render();
    var c = document.querySelector('#pair-grid .prcard[data-i="' + idx + '"]'); if (c) c.focus();
  }

  /* ---------- wiring ---------- */
  function wire() {
    $("pr-cmp").addEventListener("change", function (e) { pickComparison(e.target.value); });
    $("pr-prev").addEventListener("click", function () { go(-1, playing); });
    $("pr-next").addEventListener("click", function () { go(1, playing); });
    $("prs-prev").addEventListener("click", function () { go(-1, playing); });
    $("prs-next").addEventListener("click", function () { go(1, playing); });
    $("prs-play").addEventListener("click", function () { $("cv-play").click(); });
    $("pr-scores").addEventListener("change", function (e) { $("pairs").classList.toggle("scores-on", e.target.checked); });
    $("pr-hand").addEventListener("click", function () { open = true; toHand({}); render(); $("cv-test").focus(); });
    $("pr-back").addEventListener("click", function () { leaveHand(); refilter(); render(); openCurrent(false); syncUrl(); });
    document.addEventListener("pwa:playing", function (e) {
      playing = !!e.detail;
      var b = $("prs-play"); b.textContent = playing ? "Pause" : "Play"; b.setAttribute("aria-label", playing ? "Pause both clips" : "Play both clips");
    });
    // auto next: a non-looping play reached its end
    document.addEventListener("pwa:ended", function () {
      if (hand || !$("cv-auto").checked) return;
      if (!go(1, true)) $("cv-auto").checked = false;
    });
    // findings and the tour: a task from two runs
    document.addEventListener("pwa:openpair", function (e) {
      var d = e.detail || {};
      if (!D) { setTimeout(function () { document.dispatchEvent(new CustomEvent("pwa:openpair", { detail: d })); }, 300); return; }
      var m = mapLegacy(D, d.task || "", d.b || "", d.c || "");
      if (m) { open = true; selectPair(m.cmp, m.task, m.ctl, m.trt, !!d.play && !lazy()); }
      else { open = true; toHand({ task: d.task, b: d.b, c: d.c, play: !!d.play, note: "Not a derived control/treatment pair: different seed or flags." }); render(); }
    });
    // "compare with control" links in the findings open in place
    document.addEventListener("click", function (e) {
      var a = e.target && e.target.closest ? e.target.closest('a[href^="?compare="]') : null;
      if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
      var q = new URLSearchParams(a.getAttribute("href").split("#")[0]);
      if (q.get("a")) return;
      e.preventDefault();
      document.dispatchEvent(new CustomEvent("pwa:openpair", { detail: { task: q.get("compare"), b: q.get("b"), c: q.get("c"), play: false } }));
      scrollToPlayer();
    });
    // keys inside the section; form fields keep their own keys
    $("pairs").addEventListener("keydown", function (e) {
      var tg = e.target && e.target.tagName;
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      if (tg === "SELECT" || tg === "TEXTAREA" || tg === "INPUT" && e.target.type !== "range" && e.target.type !== "checkbox") return;
      var k = e.key, onBtn = tg === "BUTTON" || tg === "SUMMARY" || tg === "A";
      if (!hand && (k === "ArrowRight" || k === "k" || k === "K") && tg !== "INPUT" && !e.target.closest("[role=tablist]")) { e.preventDefault(); go(1, playing); }
      else if (!hand && (k === "ArrowLeft" || k === "j" || k === "J") && tg !== "INPUT" && !e.target.closest("[role=tablist]")) { e.preventDefault(); go(-1, playing); }
      else if (k === " " && !onBtn && tg !== "INPUT") { e.preventDefault(); $("cv-play").click(); }
      else if (k === "," || k === ".") { e.preventDefault(); $(k === "," ? "cv-back" : "cv-fwd").click(); }
      else if (k === "1" || k === "2" || k === "3") { document.dispatchEvent(new CustomEvent("pwa:rate", { detail: k === "1" ? "0.5" : k === "2" ? "1" : "2" })); }
      else if (k === "l" || k === "L") { $("cv-loop").click(); }
      else if (k === "s" || k === "S") { $("cv-swap").click(); }
      else if (k === "f" || k === "F") { e.preventDefault(); e.stopPropagation(); $("cv-full").click(); }
      else if (k === "Escape" && !hand && open) { closePlayer(); }
    });
  }

  if (!$("pairs")) return;
  wire();
  if (window.PWA_SITE) start(); else document.addEventListener("pwa:data", start);
})();
