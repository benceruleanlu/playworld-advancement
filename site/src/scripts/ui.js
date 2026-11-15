// DOM and display helpers shared by app.js and compare.js.
export function $(id) { return document.getElementById(id); }
export function el(tag, attrs, kids) {
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
// A failing pass (gate, IF/OE check, error) that is not the representative one keeps its own reason under it.
export function judgeComment(t, open) {
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
export function passesText(t) {
  var ps = t.pass_scores || [];
  return ps.length ? "per pass " + ps.map(function (v) { return typeof v === "number" ? String(Math.round(v * 100) / 100) : "-"; }).join("/") : null;
}
export function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
export function fmt(x, d) { return typeof x === "number" ? x.toFixed(d === undefined ? 2 : d) : "-"; }
// one pill style for every status label: cls is "", "ok", "warn" or "bad"
export function badge(cls, text, title) { return el("span", { class: "badge" + (cls ? " " + cls : ""), text: text, title: title || null }); }
// a segmented control (role tablist): items [[value, label]], current value, onPick(value)
export function segmented(label, items, current, onPick) {
  var box = el("div", { class: "tabs", role: "tablist", "aria-label": label });
  items.forEach(function (it, i) {
    var b = el("button", { type: "button", role: "tab", "aria-selected": String(it[0] === current), tabindex: it[0] === current ? "0" : "-1", text: it[1] });
    b.addEventListener("click", function () { onPick(it[0]); });
    b.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault(); onPick(items[(i + (e.key === "ArrowRight" ? 1 : items.length - 1)) % items.length][0], true);
    });
    box.appendChild(b);
  });
  return box;
}
