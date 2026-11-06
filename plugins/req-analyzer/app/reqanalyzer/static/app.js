"use strict";
const $ = (s) => document.querySelector(s);

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v; else e.setAttribute(k, v);
  }
  for (const k of kids) if (k != null) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
}

// Icons from the sprite in index.html (UEUIS §8.6); decorative, so hidden from assistive tech.
const SVGNS = "http://www.w3.org/2000/svg";
function icon(name, cls) {
  const svg = document.createElementNS(SVGNS, "svg");
  svg.setAttribute("class", "ic" + (cls ? " " + cls : "")); svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVGNS, "use"); use.setAttribute("href", "#i-" + name);
  svg.append(use); return svg;
}
function chip(text, tone, iconName) {
  return el("span", { class: "chip c-" + tone }, iconName ? icon(iconName) : null, text);
}
// Score bands and verdicts share one colour mapping everywhere (UEUIS §8.3).
function band(verdict) {
  const v = String(verdict || "").toLowerCase();
  if (v.startsWith("reuse")) return { tone: "success", icon: "check", word: "Reuse" };
  if (v.startsWith("fork") || v.startsWith("extend")) return { tone: "info", icon: "branch", word: "Fork / extend" };
  if (v.startsWith("borrow")) return { tone: "warning", icon: "layers", word: "Borrow parts" };
  if (v.includes("insufficient evidence")) return { tone: "warning", icon: "alert", word: "Insufficient evidence" };
  return { tone: "neutral", icon: "build", word: "Build new" };
}
// 2.0 per-candidate assessment: recommendation, evidence confidence, licence, compatibility, maintenance.
const LIC_TONE = { allowed: "success", review: "warning", "learn-only": "danger" };
function assessCell(x) {
  const ev = x.evidence || {}, lic = x.licence || {}, m = x.maintenance || {};
  const rb = band(x.recommendation || "");
  return el("td", {}, el("div", { class: "assess" },
    chip(x.recommendation || "—", rb.tone, rb.icon),
    el("span", { class: "tag", title: "Evidence confidence (heuristic, uncalibrated): " + (ev.sources || []).join(", ") }, `evidence ${ev.confidence ?? 0}%`),
    lic.spdx ? el("span", { class: "tag c-" + (LIC_TONE[lic.reuse] || "neutral"), title: lic.reason || "" }, `${lic.spdx}: ${lic.reuse}`) : null,
    x.compatibility && x.compatibility !== "unknown" ? el("span", { class: "tag c-" + (x.compatibility === "pass" ? "success" : "danger"),
      title: (x.compatibility_reasons || []).join("; ") }, "compat " + x.compatibility) : null,
    m.state && m.state !== "unknown" ? el("span", { class: "tag" + (m.state === "active" ? "" : " c-warning") }, m.state) : null,
    ev.readme_inspected ? el("span", { class: "tag c-violet", title: "Concepts confirmed in the README: " + (ev.confirmed_in_readme || []).join(", ") }, "README checked") : null,
    x.semantic ? el("span", { class: "tag c-" + (x.semantic.fit >= 70 ? "success" : x.semantic.fit >= 40 ? "warning" : "neutral"),
      title: `Claude's judgement (uncalibrated): ${x.semantic.reason} Covers: ${x.semantic.covers.join(", ") || "—"}. Gaps: ${x.semantic.gaps.join(", ") || "—"}.` },
      `fit ${x.semantic.fit}% (Claude)`) : null));
}
function renderDecision(d) {
  const box = $("#decision");
  if (!d) { box.replaceChildren(); return; }
  const b = band(d.recommendation);
  const opts = (d.options || []).map((o) => el("div", { class: "opt" }, el("strong", {}, o.candidate), el("div", {}, `${o.strategy} · coverage ${o.coverage}% · evidence ${o.confidence}%`),
    el("div", {}, o.effort ? `reuse effort ${o.effort.low}–${o.effort.high} units` : "cannot copy: licence")));
  box.replaceChildren(
    el("h3", { id: "dec-h" }, icon("chart"), "Reuse or build? ", chip(b.word, b.tone, b.icon),
      el("span", { class: "tag" }, `build new ${d.build_new.low}–${d.build_new.high} ${d.units}`), el("span", { class: "tag" }, "confidence " + d.confidence)),
    opts.length ? el("div", { class: "opts" }, ...opts) : el("p", { class: "small" }, "No candidate covers 30% or more of the requirement."),
    el("ul", { class: "desc-only" }, ...(d.sensitivity || []).map((t) => el("li", {}, t)), ...(d.assumptions || []).map((t) => el("li", { class: "small" }, t))));
}
// Categorical palette (UEUIS §8.16): k1..k5 give non-status items their own colour; 0 keeps the status tone.
function kTile(t, k) { if (k) t.classList.add("k" + k); return t; }
function tile(label, value, note, tone, iconName) {
  return el("div", { class: "tile t-" + tone }, el("div", { class: "eyebrow" }, icon(iconName), label),
    el("div", { class: "value" }, value), note ? el("div", { class: "note" }, note) : null);
}
const STATUS = { succeeded: ["success", "check"], failed: ["danger", "x"], "timed-out": ["danger", "clock"], timed_out: ["danger", "clock"],
  interrupted: ["danger", "alert"], cancelled: ["neutral", "stop"], running: ["warning", null], queued: ["info", "clock"],
  created: ["info", "clock"], validated: ["info", "clock"], preparing: ["warning", null], verifying: ["warning", null],
  partially_completed: ["warning", "alert"], blocked: ["danger", "alert"] };
const ACTIVE = new Set(["created", "validated", "queued", "preparing", "running", "verifying"]);
const GATE_TONE = { VERIFIED: ["success", "check"], NOT_VERIFIED: ["warning", "alert"], FAILED: ["danger", "x"], BLOCKED: ["danger", "alert"], "N/A": ["neutral", "info"] };
function statusChip(st) {
  const [tone, ic] = STATUS[st] || ["neutral", "info"];
  const c = chip(String(st).replace(/_/g, " "), tone, ic);
  if (!ic) c.prepend(el("span", { class: "dot", "aria-hidden": "true" }));
  return c;
}

// One score mapping everywhere (UEUIS §8.3): the verdict bands 70 / 50 / 30.
function scoreBand(p) { return p >= 70 ? "p-hi" : p >= 50 ? "p-info" : p >= 30 ? "p-mid" : "p-lo"; }
const BAND_WORD = { "p-hi": "reuse band", "p-info": "fork band", "p-mid": "borrow band", "p-lo": "build-new band" };
// Bullet graph (Few): grey qualitative bands at 30/50/70, value bar, target tick at 70 (UEUIS §8.11).
function bullet(p) {
  const b = el("div", { class: "bullet", "aria-hidden": "true" }, el("span", { class: "val" }), el("span", { class: "tgt" }));
  b.firstChild.style.width = Math.max(2, Math.min(100, p)) + "%";
  return b;
}
// Toasts (UEUIS §8.11): brief confirmations, 6 s, dismissible; never the only copy of information.
function toast(msg, iconName) {
  const t = el("div", { class: "toast" }, icon(iconName || "check"), el("span", {}, msg));
  const x = el("button", { type: "button", class: "ghost", "aria-label": "Dismiss" }, "×");
  x.addEventListener("click", () => t.remove());
  t.append(x); $("#toasts").append(t);
  setTimeout(() => t.remove(), 6000);
}
function rel(ts) {
  if (!ts) return "—";
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 45) return "just now";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  if (s < 86400) return Math.round(s / 3600) + " h ago";
  return Math.round(s / 86400) + " d ago";
}
// Relative time with the absolute local time beside it (UEUIS §8.8).
function whenCell(ts) {
  return el("td", { class: "nowrap" }, el("span", { class: "when" }, rel(ts), el("small", {}, fmtTime(ts))));
}
function copyBtn(text, label) {
  const b = el("button", { type: "button", class: "ghost copy", "aria-label": "Copy " + label, title: "Copy " + label.toLowerCase() }, icon("copy"));
  b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); toast(label + " copied", "copy"); }
    catch { toast("Copy is blocked by the browser; select the text instead", "alert"); }
  });
  return b;
}

// Busy state for a button: spinner + new label, restored afterwards (UEUIS §8.14).
function setBusy(btn, on, label) {
  if (on) { btn.dataset.html = btn.innerHTML; btn.replaceChildren(el("span", { class: "spin", "aria-hidden": "true" }), label); btn.setAttribute("aria-busy", "true"); btn.disabled = true; }
  else { if (btn.dataset.html) btn.innerHTML = btn.dataset.html; btn.removeAttribute("aria-busy"); btn.disabled = false; }
}
function compact(n) { return Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(n || 0); }
function relDate(d) { const t = Date.parse(d); return Number.isNaN(t) ? (d || "unknown") : rel(t / 1000); }
// Mobile card layout reads each cell's column name from the header (UEUIS §9).
function labelCells(tableSel) {
  const heads = [...document.querySelectorAll(tableSel + " thead th")].map((h) => h.textContent.trim());
  for (const tr of document.querySelectorAll(tableSel + " tbody tr")) {
    [...tr.children].forEach((td, i) => { if (!td.hasAttribute("colspan") && heads[i]) td.setAttribute("data-label", heads[i]); });
  }
}
// Long descriptions: three lines, then "Show more" (UEUIS §3: nothing is hidden for good).
function clampCell(text, extra) {
  const p = el("div", { class: "clamp" }, text);
  const td = el("td", { class: "desc" }, p);
  if (String(text).length > 220) {
    const b = el("button", { type: "button", class: "more-btn", "aria-expanded": "false" }, "Show more");
    b.addEventListener("click", () => { const open = p.classList.toggle("open"); b.textContent = open ? "Show less" : "Show more"; b.setAttribute("aria-expanded", String(open)); });
    td.append(b);
  }
  if (extra) td.append(extra);
  return td;
}
function gapsCell(missing) {
  return el("td", {}, missing.length ? el("div", { class: "gaps" }, ...missing.map((m) => el("span", { class: "tag" }, m)))
    : chip("covers all", "success", "check"));
}

const REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
function reveal(node) { node.scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "start" }); }

// An external link that says it opens a new tab (UEUIS §5, WCAG 3.2.5 advisory).
function extLink(href, text) {
  return el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text, el("span", { class: "sr-only" }, " (opens in a new tab)"));
}

// A table body showing one message row: loading, empty or error (UEUIS §6, empty-state format §8.7).
function messageRow(tbody, cols, text, cls, title, iconName) {
  const td = el("td", { colspan: String(cols), class: cls || "small" });
  if (title) { td.className = "empty"; td.append(icon(iconName || "info", "xl"), el("strong", {}, title), text); }
  else td.append(cls === "err" ? icon("alert") : "", " ", text);
  tbody.replaceChildren(el("tr", {}, td));
}

/* ------------------------------------------------------------ theme (UEUIS §8) */
// Segmented radio group: System / Light / Dark; arrow keys move and select (WAI-ARIA radio group pattern).
const THEMES = ["system", "light", "dark"];
function setTheme(v, focus) {
  if (v === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", v);
  for (const b of document.querySelectorAll("#theme [role=radio]")) {
    const on = b.dataset.v === v;
    b.setAttribute("aria-checked", String(on)); b.tabIndex = on ? 0 : -1;
    if (on && focus) b.focus();
  }
  try { localStorage.setItem("reqan-theme", v); } catch { /* storage unavailable */ }
}
(function () {
  let t = "system";
  try { t = localStorage.getItem("reqan-theme") || "system"; } catch { /* storage unavailable */ }
  setTheme(THEMES.includes(t) ? t : "system");
  $("#theme").addEventListener("click", (e) => { const b = e.target.closest("[role=radio]"); if (b) setTheme(b.dataset.v); });
  $("#theme").addEventListener("keydown", (e) => {
    const cur = THEMES.indexOf(document.querySelector("#theme [aria-checked=true]").dataset.v);
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (step) { e.preventDefault(); setTheme(THEMES[(cur + step + 3) % 3], true); }
  });
})();

/* ------------------------------------------------------------ descriptions switch (UEUIS §8.18) */
function setDesc(show) {
  document.documentElement.classList.toggle("hide-desc", !show);
  $("#desc-toggle").setAttribute("aria-checked", String(show));
  try { localStorage.setItem("reqan-desc", show ? "show" : "hide"); } catch { /* storage unavailable */ }
}
setDesc(!document.documentElement.classList.contains("hide-desc"));
$("#desc-toggle").addEventListener("click", () => setDesc($("#desc-toggle").getAttribute("aria-checked") !== "true"));

function safeUrl(u) {
  try { const x = new URL(u); return x.protocol === "https:" ? x.href : null; } catch { return null; }
}

function pctCell(p) {
  const cls = scoreBand(p);
  return el("td", { class: "pct " + cls }, el("strong", {}, p + "%"), bullet(p), el("span", { class: "sr-only" }, ` (${BAND_WORD[cls]})`));
}

function nameCell(x, tags, kind) {
  const u = safeUrl(x.url);
  const [owner, repo] = kind === "gh" && x.name.includes("/") ? x.name.split("/", 2) : [null, x.name];
  const name = u ? extLink(u, repo) : el("strong", {}, repo);
  const av = el("span", { class: "avatar " + (kind === "gh" ? "k1" : "k3") }, icon(kind === "gh" ? "branch" : "plug"));
  const body = el("div", {}, owner ? el("span", { class: "owner" }, owner + " /") : null, name);
  const tone = { reviewed: "success", "claude plugin": "violet", archived: "warning" };
  return el("td", {}, el("div", { class: "who" }, av, body), el("div", {}, ...tags.filter(Boolean).map((t) => el("span", { class: "tag " + (tone[t] ? "c-" + tone[t] : "") }, t))));
}

// Distribution of every match across the verdict bands (UEUIS §8.11, IBCS-style stacked bar).
function renderDist(items) {
  const bands = [["success", "Reuse ≥70%", (p) => p >= 70], ["info", "Fork 50–69%", (p) => p >= 50 && p < 70],
    ["warning", "Borrow 30–49%", (p) => p >= 30 && p < 50], ["neutral", "Build new <30%", (p) => p < 30]];
  const counts = bands.map(([, , f]) => items.filter((x) => f(x.closeness)).length);
  const total = items.length || 1;
  const stack = el("div", { class: "stack", role: "img", "aria-label": "Matches by band: " +
    bands.map(([, label], i) => `${label}: ${counts[i]}`).join(", ") });
  bands.forEach(([tone], i) => { if (counts[i]) { const sp = el("span", { class: "b-" + tone }); sp.style.width = (100 * counts[i] / total) + "%"; stack.append(sp); } });
  const legend = el("div", { class: "legend" }, ...bands.map(([tone, label], i) =>
    el("span", { class: "k" }, el("span", { class: "sw b-" + tone }), el("span", {}, label + " ", el("strong", { class: "num" }, String(counts[i]))))));
  $("#dist").replaceChildren(el("h3", {}, icon("chart"), `${items.length} matches by band`), stack, legend);
}

// Skeleton placeholders while an analysis runs (UEUIS §8.11).
function skeleton() {
  $("#out").hidden = false; $("#out").setAttribute("aria-busy", "true");
  $("#verdict").className = "verdict"; $("#verdict").replaceChildren(el("span", { class: "skel w60 tall" }));
  $("#tiles").replaceChildren(...[1, 2, 3, 4, 5].map(() => el("div", { class: "tile t-neutral" }, el("span", { class: "skel w40" }),
    el("span", { class: "skel tall w60" }), el("span", { class: "skel w80" }))));
  $("#dist").replaceChildren(el("span", { class: "skel w40" }), el("span", { class: "skel" }));
  for (const [id, cols] of [["#pt", 4], ["#gt", 5], ["#kt", 5]]) {
    $(id + " tbody").replaceChildren(...[1, 2, 3].map(() => el("tr", {}, ...Array.from({ length: cols }, () => el("td", {}, el("span", { class: "skel" }))))));
  }
}

function render(r) {
  $("#out").hidden = false;
  const b = band(r.verdict);
  const vd = $("#verdict");
  vd.className = "verdict v-" + b.tone;
  vd.replaceChildren(el("span", { class: "icon-tile" }, icon(b.icon, "lg")), el("span", { id: "verdict-text" }, r.best
    ? `${r.verdict} — best match ${r.best.name} at ${r.best.closeness}%`
    : r.verdict));
  // Recommended next steps right on the verdict (UEUIS §8.14)
  const va = el("div", { class: "va" });
  const bu = r.best && safeUrl(r.best.url);
  if (bu) va.append(el("a", { href: bu, target: "_blank", rel: "noopener noreferrer", class: "linkbtn" },
    icon("ext"), "Open best match", el("span", { class: "sr-only" }, " (opens in a new tab)")));
  const nb = el("button", { type: "button" }, icon("build"), "Build reusing it");
  nb.addEventListener("click", () => { selectTab("build"); $("#tab-build").focus(); });
  va.append(nb); vd.append(va);
  document.documentElement.classList.add("has-results");   // the requirement box gives the results the room
  document.title = `${b.word}: ${r.best ? r.best.closeness + "% " + r.best.name : "no match"} · Reuse-First Builder`;
  const bp = r.best ? r.best.closeness : 0;
  const bestBand = { "p-hi": "success", "p-info": "info", "p-mid": "warning", "p-lo": "neutral" }[scoreBand(bp)];
  const bestTile = tile("Best match", r.best ? bp + "%" : "—", r.best ? r.best.name : "No match shares a key concept", bestBand, "star");
  bestTile.classList.add(scoreBand(bp));
  bestTile.append(bullet(bp), el("div", { class: "scale", "aria-hidden": "true" }, el("span", {}, "0"), el("span", {}, "30"),
    el("span", {}, "50"), el("span", {}, "70 reuse"), el("span", {}, "100")));
  $("#tiles").replaceChildren(
    bestTile,
    tile("Verdict", b.word, "≥70 reuse · 50–69 fork · 30–49 borrow", b.tone, b.icon),
    kTile(tile("Claude plugins", String(r.claude_plugins.length), `of ${Number(r.catalog_size).toLocaleString()} indexed`, "violet", "plug"), 3),
    kTile(tile("GitHub repos", String(r.github.length), "GitHub: " + r.github_status, r.github_status === "ok" ? "info" : "warning", "branch"), r.github_status === "ok" ? 1 : 0),
    kTile(tile("Time", r.elapsed_s + " s", `${r.concepts.length} key concepts`, "accent", "gauge"), 5));
  $("#meta").textContent = `Key concepts: ${r.concepts.join(", ") || "(none)"} · ` +
    `GitHub: ${r.github_status}${r.github_authenticated ? " (authenticated)" : r.github_authenticated === false ? " (unauthenticated, 10 searches/min)" : ""}` +
    ` · ${r.catalog_size} Claude plugins indexed · ${r.elapsed_s}s`;
  renderDist([...r.claude_plugins, ...r.github, ...(r.packages || [])]);
  renderDecision(r.decision);
  STATE.analysisId = r.saved ? r.saved.id : null;
  $("#out").removeAttribute("aria-busy");
  STATE.analyzed = true;
  const errs = $("#errors"); errs.replaceChildren();
  for (const e of r.errors) errs.append(el("div", { class: "warn" }, icon("alert"), el("span", {}, e)));

  const pt = $("#pt tbody"); pt.replaceChildren();
  for (const x of r.claude_plugins) {
    pt.append(el("tr", { "data-text": `${x.name} ${x.description} ${x.category || ""}`.toLowerCase() }, pctCell(x.closeness),
      nameCell(x, [x.reviewed ? "reviewed" : null, x.category || null], "plugin"),
      clampCell(x.description, el("div", { class: "meta-line" }, x.source, assessCell(x).firstChild)),
      gapsCell(x.missing)));
  }
  if (!r.claude_plugins.length) messageRow(pt, 4, "Describe in more detail what the app must do.", "", "No Claude plugin shares a key concept", "plug");
  $("#pc").textContent = `(top ${r.claude_plugins.length})`;

  const gt = $("#gt tbody"); gt.replaceChildren();
  for (const x of r.github) {
    // GitHub reports NOASSERTION when a licence file exists but is not a recognised one; "none" means no licence file.
    const lic = !x.license || x.license === "none" ? chip("no license", "warning", "alert")
      : x.license === "NOASSERTION" ? chip("other license", "neutral", "info") : chip(x.license, "neutral");
    gt.append(el("tr", { "data-text": `${x.name} ${x.description || ""} ${x.language || ""}`.toLowerCase() }, pctCell(x.closeness),
      nameCell(x, [x.is_claude_plugin ? "claude plugin" : null, x.archived ? "archived" : null, x.language || null], "gh"),
      clampCell(x.description || "(no description)"),
      el("td", {}, el("div", { class: "meta-line" }, el("span", { title: x.stars.toLocaleString() + " stars" }, icon("star"), " " + compact(x.stars)),
        lic, el("span", { title: "Last push " + (x.updated || "unknown") }, icon("clock"), " " + relDate(x.updated))), assessCell(x).firstChild),
      gapsCell(x.missing)));
  }
  if (!r.github.length) messageRow(gt, 5, r.github_status === "skipped" ? "Tick Search GitHub and analyze again."
    : "See the warnings above, or describe the app in more detail.", "", r.github_status === "skipped" ? "GitHub search was turned off" : "No repositories found", "branch");
  $("#gc").textContent = `(top ${r.github.length})`;
  const kt = $("#kt tbody"); kt.replaceChildren();
  for (const x of r.packages || []) {
    kt.append(el("tr", { "data-text": `${x.name} ${x.description || ""} ${x.ecosystem}`.toLowerCase() }, pctCell(x.closeness),
      nameCell(x, [x.ecosystem, x.version ? "v" + x.version : null], "plugin"), clampCell(x.description || "(no description)"),
      assessCell(x), gapsCell(x.missing)));
  }
  if (!(r.packages || []).length) messageRow(kt, 5, "Package registries are searched together with GitHub.", "", "No packages found", "layers");
  $("#kc").textContent = `(top ${(r.packages || []).length})`;
  labelCells("#kt");
  $("#method").textContent = "How relevance is computed: " + r.method + (r.confidence_mode ? " Mode: " + r.confidence_mode + "." : "") +
    (r.semantic ? ` Claude review: ${r.semantic.status}, ${r.semantic.reviewed} candidates` + (r.semantic.cost_usd != null ? `, model-reported $${r.semantic.cost_usd.toFixed(2)}.` : ".") : "") +
    (r.stale ? " Some GitHub results come from a cache older than 10 minutes." : "");
  labelCells("#pt"); labelCells("#gt");
  $("#filter").value = ""; applyFilter();
}

// Results filter (UEUIS §8.14): narrows both tables, says how many rows remain.
function applyFilter() {
  const q = $("#filter").value.trim().toLowerCase();
  let shown = 0, total = 0;
  for (const tr of document.querySelectorAll("#pt tbody tr[data-text], #gt tbody tr[data-text], #kt tbody tr[data-text]")) {
    total++; const hit = !q || tr.dataset.text.includes(q); tr.hidden = !hit; if (hit) shown++;
  }
  $("#fcount").textContent = q ? `Showing ${shown} of ${total}` : `${total} results`;
}
$("#filter").addEventListener("input", applyFilter);

$("#f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const requirement = $("#req").value.trim();
  const status = $("#status");
  status.className = "";
  if (!requirement) { status.className = "err"; status.textContent = "Enter a requirement first."; markReq(true); $("#req").focus(); return; }
  markReq(false);
  setBusy($("#go"), true, "Analyzing…");
  document.title = "Analyzing… · Reuse-First Builder";
  status.textContent = $("#sem").checked ? "Analyzing… then Claude reviews the top candidates (about 30–90 s)"
    : $("#gh").checked ? "Analyzing… (searching GitHub, up to ~20 s)" : "Analyzing…";
  skeleton();
  try {
    const data = await api("/api/analyze", { method: "POST", body: JSON.stringify({ requirement, github: $("#gh").checked, top: 10, semantic: $("#sem").checked }) });
    render(data);
    status.textContent = data.saved ? `Done. Saved ${fmtTime(data.saved.created_at)}.` : "Done.";
    status.className = "ok";
    if (data.saved) toast("Analysis saved to Previous analyses", "check");
    loadAnalyses();
  } catch (e) {
    status.className = "err";
    status.textContent = "Failed: " + e.message;
    if (!STATE.analyzed) $("#out").hidden = true;
    $("#out").removeAttribute("aria-busy");
  } finally {
    setBusy($("#go"), false);
  }
});

function markReq(bad) {
  if (bad) $("#req").setAttribute("aria-invalid", "true"); else $("#req").removeAttribute("aria-invalid");
}
function updateCount() {
  const n = $("#req").value.length;
  const c = $("#req-count"); c.textContent = `${n.toLocaleString()} / 5,000`; c.classList.toggle("near", n > 4500);
}
$("#req").addEventListener("input", () => { if ($("#req").value.trim()) markReq(false); updateCount(); });
// Keyboard shortcuts (UEUIS §10.2): Ctrl/Cmd+Enter analyzes; "/" jumps to the results filter.
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !$("#panel-analyze").hidden) { e.preventDefault(); $("#f").requestSubmit(); }
  else if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) && !$("#out").hidden) { e.preventDefault(); $("#filter").focus(); }
});
for (const b of document.querySelectorAll("#examples button")) {
  b.addEventListener("click", () => { $("#req").value = b.dataset.req; updateCount(); markReq(false); $("#req").focus(); });
}
// The navigation bar gains a divider once it sticks (pure presentation).
new IntersectionObserver(([en]) => $("#navbar").classList.toggle("stuck", en.intersectionRatio < 1),
  { threshold: [1], rootMargin: "-1px 0px 0px 0px" }).observe($("#navbar"));

/* ------------------------------------------------------------ workflow state (the numbered tabs show the order) */
const STATE = { analyzed: false, inputs: false, build: null };

/* ------------------------------------------------------------ status strip (UEUIS §8.11) */
let CHECKED = 0, STATUS_OPEN = false;
// The status details are a popover: Escape or a click elsewhere closes it (WAI-ARIA disclosure).
function closeStatus() {
  const list = $("#st-items"), sum = document.querySelector(".statusbar .sum");
  if (list && !list.hidden && !document.querySelector(".statusbar .st.bad")) { STATUS_OPEN = false; list.hidden = true; sum.setAttribute("aria-expanded", "false"); }
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeStatus(); });
document.addEventListener("click", (e) => { if (!e.target.closest(".statusbar")) closeStatus(); });
function st(text, ok, iconName) {
  return el("span", { class: "st" + (ok ? "" : " bad") }, icon(iconName || (ok ? "check" : "alert")), text);
}
async function loadStatus() {
  const bar = $("#statusbar");
  try {
    const h = await (await fetch("/api/health")).json();
    CHECKED = Date.now();
    // ISA-101 calm display: one summary when all is well; problems are always shown, details on demand.
    const items = [
      [`Server v${h.version} · up ${Math.floor(h.uptime_s / 60)} min`, h.ok ? "good" : "bad", "server"],
      [`${Number(h.catalog_size).toLocaleString()} plugins indexed`, h.catalog_size > 0 && !h.catalog_errors ? "good" : "bad", "plug"],
      [h.github_authenticated ? "GitHub: signed in" : "GitHub: anonymous, 10 searches/min", h.github_authenticated ? "good" : "note", "branch"],
      [h.claude_cli ? "Claude CLI ready" : "Claude CLI missing: builds disabled", h.claude_cli ? "good" : "bad", h.claude_cli ? "check" : "alert"],
      [h.sandbox_ok ? `Build sandbox verified (${h.resource_control})` : "No verified sandbox: builds blocked, analysis works", h.sandbox_ok ? "good" : "bad", "shield"],
      [h.standard_found && h.ui_standard_found ? "UAISES + UEUIS found" : "Standard file missing: builds refuse", h.standard_found && h.ui_standard_found ? "good" : "bad", "shield"],
      [h.build_running ? "Build running" : "No build running", h.build_running ? "note" : "good", h.build_running ? "build" : "check"]];
    const bad = items.filter((i) => i[1] === "bad");
    const pill = (t, cls, ic) => el("span", { class: "st " + cls }, icon(ic), t);
    const open = STATUS_OPEN || bad.length > 0;
    // the summary pill itself toggles the details: one control instead of two
    const sum = el("button", { type: "button", class: "st sum " + (bad.length ? "bad" : "good"), "aria-expanded": String(open), "aria-controls": "st-items" },
      icon(bad.length ? "alert" : "check"), bad.length ? `${bad.length} problem${bad.length > 1 ? "s" : ""} need attention` : "All systems ready", icon("chev", "chev"));
    const list = el("span", { class: "items", id: "st-items" }, ...items.filter((i) => i[1] !== "bad" || !bad.length).map(([t, c, ic]) => pill(t, c, ic)));
    list.hidden = !open;
    sum.addEventListener("click", () => { STATUS_OPEN = list.hidden; list.hidden = !STATUS_OPEN; sum.setAttribute("aria-expanded", String(STATUS_OPEN)); });
    list.append(el("span", { class: "fresh", id: "fresh" }, "checked just now"));
    bar.replaceChildren(sum, ...bad.map(([t, c, ic]) => pill(t, c, ic)), list);
    $("#foot-meta").firstChild.textContent = `Reuse-First Builder v${h.version} · up ${Math.floor(h.uptime_s / 60)} min`;
  } catch (e) {
    bar.replaceChildren(st("Server unreachable: " + e.message + ". Retrying every 30 s.", false));
  }
}
setInterval(() => { const f = $("#fresh"); if (f && CHECKED) f.textContent = `checked ${Math.round((Date.now() - CHECKED) / 1000)} s ago · next in ${Math.max(0, 30 - Math.round((Date.now() - CHECKED) / 1000))} s`; }, 5000);
setInterval(loadStatus, 30000);
loadStatus();

/* ------------------------------------------------------------ tabs */
const TABS = ["analyze", "build", "history"];
function selectTab(name) {
  for (const t of TABS) {
    const on = t === name;
    $("#tab-" + t).setAttribute("aria-selected", String(on));
    $("#tab-" + t).tabIndex = on ? 0 : -1;
    $("#panel-" + t).hidden = !on;
  }
  try { localStorage.setItem("reqan-tab", name); } catch { /* storage unavailable */ }
  if (name === "build") { loadBuilds(); loadApps(); }
  if (name === "history") loadAnalyses();
  // History is a page of its own: the requirement editor is not part of it (UEUIS §8.19)
  document.querySelector(".card.lead").hidden = name === "history";
}
$("#tab-analyze").addEventListener("click", () => selectTab("analyze"));
$("#tab-build").addEventListener("click", () => selectTab("build"));
$("#tab-history").addEventListener("click", () => selectTab("history"));
document.querySelector(".tabs").addEventListener("keydown", (e) => {
  let next = null;
  const cur = TABS.findIndex((t) => $("#tab-" + t).getAttribute("aria-selected") === "true");
  if (e.key === "ArrowRight") next = TABS[(cur + 1) % TABS.length];
  else if (e.key === "ArrowLeft") next = TABS[(cur + TABS.length - 1) % TABS.length];
  else if (e.key === "Home") next = TABS[0];
  else if (e.key === "End") next = TABS[TABS.length - 1];
  if (next) { e.preventDefault(); selectTab(next); $("#tab-" + next).focus(); }
});
try { const t = localStorage.getItem("reqan-tab"); if (TABS.includes(t) && t !== "analyze") selectTab(t); } catch { /* ignore */ }

/* ------------------------------------------------------------ build */
let TOKEN = null, FIELDS = [], POLL = null, JOB = null, SEEN = 0, IDEM = null;

async function api(path, opts = {}) {
  if (!TOKEN) {
    const m = /(?:^|[#&])token=([\w-]{16,128})/.exec(location.hash);   // strict mode: link printed by the plugin
    if (m) { TOKEN = m[1]; history.replaceState(null, "", location.pathname); }
    else {
      const r = await fetch("/api/session");
      if (!r.ok) throw new Error("this server needs the link with the token (strict mode); ask Claude for the ReuseFirst link");
      TOKEN = (await r.json()).token;
    }
  }
  const res = await fetch(path, { ...opts, headers: { "Content-Type": "application/json", "X-ReqAn-Token": TOKEN || "", ...(opts.headers || {}) } });
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function renderField(f) {
  const id = "in-" + f.id;
  const wrap = el("div", { class: "field" });
  const star = f.required ? [el("span", { class: "req-star", "aria-hidden": "true" }, " *"), el("span", { class: "sr-only" }, " (required)")] : [];
  const helpId = f.help ? id + "-help" : null;
  const lab = el("label", { for: id }, f.label, ...star,
    f.uaises ? el("span", { class: "tag" }, "UAISES " + f.uaises) : null,
    f.source === "claude" ? el("span", { class: "tag c-violet" }, icon("spark"), " pre-filled by Claude") : null);
  let input;
  if (f.type === "textarea") {
    input = el("textarea", { id, rows: String(Math.min(10, Math.max(3, String(f.default).split("\n").length + 1))), maxlength: "4000" });
    input.value = f.default ?? "";
  } else if (f.type === "select") {
    input = el("select", { id });
    for (const o of f.options || []) { const op = el("option", {}, o); op.value = o; if (o === f.default) op.selected = true; input.append(op); }
  } else if (f.type === "boolean") {
    input = el("input", { id, type: "checkbox" }); input.checked = !!f.default;
    wrap.append(el("label", { class: "check" }, input, " " + f.label,
      f.uaises ? el("span", { class: "tag" }, "UAISES " + f.uaises) : null));
    if (f.help) { wrap.append(el("div", { class: "help", id: helpId }, f.help)); input.setAttribute("aria-describedby", helpId); }
    return wrap;
  } else if (f.type === "number") {
    input = el("input", { id, type: "number", step: "any" }); input.value = f.default ?? "";
  } else if (f.type === "checklist") {
    input = el("div", { id, class: "checklist", role: "group", "aria-label": f.label });
    if (!(f.options || []).length) input.append(el("div", { class: "help" }, "No reuse candidates (run Analyze with GitHub on to get some)."));
    (f.options || []).forEach((o, i) => {
      const cb = el("input", { type: "checkbox", "data-val": o }); cb.checked = (f.default || []).includes(o);
      const parts = o.split(" · ");
      const url = safeUrl(parts[parts.length - 1]);
      const why = (f.not_preselected || {})[o];
      input.append(el("label", {}, cb, el("span", {}, parts.slice(0, -1).join(" · ") + " ",
        url ? extLink(url, "open") : null, why ? el("span", { class: "help" }, " Not pre-ticked: " + why.join("; ")) : null)));
    });
  } else {
    input = el("input", { id, type: "text", maxlength: "4000" }); input.value = f.default ?? "";
  }
  if (f.required && input.setAttribute) input.setAttribute("aria-required", "true");
  if (helpId) input.setAttribute("aria-describedby", helpId);
  wrap.append(lab, input);
  if (f.help) wrap.append(el("div", { class: "help", id: helpId }, f.help));
  return wrap;
}

function readAnswers() {
  const answers = {}, labels = {}, missing = [];
  for (const f of FIELDS) {
    const node = $("#in-" + f.id);
    let v;
    if (f.type === "boolean") v = node.checked;
    else if (f.type === "number") v = node.value === "" ? null : Number(node.value);
    else if (f.type === "checklist") v = [...node.querySelectorAll("input:checked")].map((c) => c.dataset.val);
    else v = node.value.trim();
    const bad = f.required && (v === "" || v == null);
    if (node.setAttribute) { if (bad) node.setAttribute("aria-invalid", "true"); else node.removeAttribute("aria-invalid"); }
    if (bad) missing.push(f);
    if (v != null) answers[f.id] = v;
    labels[f.id] = f.label;
  }
  return { answers, labels, missing };
}

let APPS_LOADED = false;
async function loadApps() {
  if (APPS_LOADED) return;
  try {
    const r = await api("/api/apps");
    const sel = $("#build-into");
    for (const a of r.apps || []) { const o = el("option", {}, "Enhance: " + a.name); o.value = a.path; sel.append(o); }
    APPS_LOADED = true;
  } catch { /* the new-app option still works */ }
}

$("#list-inputs").addEventListener("click", async () => {
  const requirement = $("#req").value.trim();
  const st = $("#bstatus"); st.className = "";
  if (!requirement) { st.className = "err"; st.textContent = "Enter a requirement first."; $("#req").focus(); return; }
  setBusy($("#list-inputs"), true, "Listing inputs…");
  $("#err-summary").hidden = true;
  st.textContent = "Listing required inputs… Claude is reading the requirement and the closest projects (about 30–90 s).";
  try {
    const target = $("#build-into").value || undefined;
    const r = await api("/api/inputs", { method: "POST", body: JSON.stringify({ requirement, target }) });
    $("#create").lastChild.textContent = r.mode === "enhance" ? " Enhance app" : " Create app";
    FIELDS = r.fields;
    const box = $("#fields"); box.replaceChildren();
    const groups = [...new Set(FIELDS.map((f) => f.group))];
    const GICON = [["Requirements", "users"], ["Non-functional", "gauge"], ["Architecture", "layers"], ["Delivery", "flag"],
      ["Run limits", "sliders"], ["App-specific", "spark"]];
    groups.forEach((g, i) => {
      const ic = (GICON.find(([k]) => g.startsWith(k)) || [null, "list"])[1];
      const fs = el("fieldset", { class: (g === "App-specific" ? "ai g4" : "g" + (i % 6)) },
        el("legend", {}, icon(ic), g === "App-specific" ? "App-specific inputs (from Claude)" : g));
      for (const f of FIELDS.filter((x) => x.group === g)) fs.append(renderField(f));
      box.append(fs);
    });
    $("#inputs").hidden = false;
    STATE.inputs = true;
    st.textContent = r.ai_status === "ok"
      ? `${FIELDS.length} inputs listed; ${FIELDS.filter((f) => f.source === "claude").length} pre-filled by Claude. Review, then ${r.mode === "enhance" ? "Enhance app" : "Create app"}.`
      : `Claude could not pre-fill the inputs (${r.ai_error}). Showing the standard inputs only; fill in the required ones (*).`;
    if (r.ai_status !== "ok") st.className = "err";
    const missingStd = [!r.standard_found && "UAISES (" + r.standard + ")", r.ui_standard_found === false && "UEUIS (" + r.ui_standard + ")"].filter(Boolean);
    $("#build-note").textContent = !missingStd.length
      ? "The build follows UAISES and the UEUIS UI standard (both copied into the app's docs/). It runs without asking questions and stops at the spending cap or time limit."
      : "Standard not found, so the build will refuse to start: " + missingStd.join("; ");
    if (missingStd.length) $("#build-note").className = "hint grow err";
  } catch (e) {
    st.className = "err"; st.textContent = "Failed: " + e.message;
  } finally { setBusy($("#list-inputs"), false); }
});

$("#inputs").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const st = $("#bstatus"); st.className = "";
  const { answers, labels, missing } = readAnswers();
  const sum = $("#err-summary");
  if (missing.length) {
    // UEUIS §4: an error summary linked to each field; every entered value is kept.
    const list = el("ul");
    for (const f of missing) {
      const a = el("a", { href: "#in-" + f.id }, f.label + " is required");
      a.addEventListener("click", (e) => { e.preventDefault(); $("#in-" + f.id).focus(); });
      list.append(el("li", {}, a));
    }
    sum.replaceChildren(el("h2", {}, `${missing.length} required input${missing.length > 1 ? "s are" : " is"} empty`), list);
    sum.hidden = false; sum.focus(); st.textContent = "";
    return;
  }
  sum.hidden = true;
  setBusy($("#create"), true, "Starting…");
  try {
    IDEM = IDEM || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
    const job = await api("/api/build", { method: "POST", headers: { "Idempotency-Key": IDEM },
      body: JSON.stringify({ requirement: $("#req").value.trim(), answers, labels, analysis_id: STATE.analysisId || undefined }) });
    IDEM = null;
    st.textContent = "Build started.";
    toast("Build started: " + answers.app_name, "build");
    watch(job.id);
  } catch (e) {
    st.className = "err"; st.textContent = "Could not start: " + e.message;
  } finally { setBusy($("#create"), false); }
});

function fmtTime(ts) { return ts ? new Date(ts * 1000).toLocaleString() : "—"; }
function dur(a, b) { if (!a) return "—"; const s = Math.round((b || Date.now() / 1000) - a); return `${Math.floor(s / 60)}m ${s % 60}s`; }

function watch(id) {
  JOB = id; SEEN = 0; $("#events").replaceChildren(); $("#job").hidden = false;
  $("#report-wrap").hidden = true; $("#launch").hidden = true; $("#stop-app").hidden = true; $("#launch-out").textContent = "";
  $("#gates-wrap").hidden = true;
  clearInterval(POLL); poll(); POLL = setInterval(poll, 2000);
  reveal($("#job"));
}

async function poll() {
  if (!JOB) return;
  let j;
  try { j = await api(`/api/builds/${encodeURIComponent(JOB)}?since=${SEEN}`); }
  catch (e) { $("#job-meta").textContent = "Lost contact with the server: " + e.message; return; }
  if (j.error && !j.id) { $("#job-meta").textContent = j.error; clearInterval(POLL); return; }
  const list = $("#events");
  for (const e of j.events) list.append(el("li", { class: "k-" + e.kind }, `[${e.t}s] `, e.text));
  if (j.events.length) list.scrollTop = list.scrollHeight;
  SEEN = j.event_count;
  const head = $("#job-head");
  head.replaceChildren(el("span", { class: "icon-tile" }, icon("build", "lg")), el("span", {}, `${j.app_name}: `), statusChip(j.status));
  $("#job-meta").replaceChildren(el("span", { class: "mono" }, j.output_dir), copyBtn(j.output_dir, "Folder path"), ` · elapsed`);
  $("#job-meta").append(` ${dur(j.started_at, j.finished_at)}` +
    (j.cost_usd != null ? ` · cost $${j.cost_usd.toFixed(2)}` : "") + (j.denials ? ` · ${j.denials} actions refused by the allowlist` : "") +
    (j.error ? ` · ${j.error}` : "") + (j.file_count != null ? ` · ${j.file_count} files` : "") +
    (j.has_reuse_doc ? " · reuse recorded in docs/REUSE.md" : "") + (j.cost_usd != null ? " (model-reported estimate, not billing)" : "") +
    (j.egress && j.egress.denied_hosts && j.egress.denied_hosts.length ? ` · sandbox refused network to ${j.egress.denied_hosts.length} host(s)` : "") +
    (j.reasons && j.reasons.length && !ACTIVE.has(j.status) ? " · " + j.reasons.join("; ") : ""));
  const live = ACTIVE.has(j.status);
  const gt = $("#gates tbody"); gt.replaceChildren();
  for (const g of j.gates || []) {
    const [tone, ic] = GATE_TONE[g.status] || ["neutral", "info"];
    gt.append(el("tr", {}, el("td", {}, g.name + (g.mandatory ? "" : " (advisory)")), el("td", {}, chip(g.status.replace(/_/g, " "), tone, ic)), el("td", { class: "small" }, g.detail)));
  }
  labelCells("#gates");
  $("#gates-wrap").hidden = !(j.gates || []).length;
  STATE.build = j.status;
  $("#cancel").hidden = !live;
  if (!live) {
    clearInterval(POLL);
    if (j.report) { $("#report").textContent = j.report; $("#report-wrap").hidden = false; }
    else if (j.result) { $("#report").textContent = j.result; $("#report-wrap").hidden = false; }
    $("#launch").hidden = !(j.status === "succeeded" && j.has_run_sh) || !!j.app_running;
    $("#stop-app").hidden = !j.app_running;
    loadBuilds();
  }
}

$("#cancel").addEventListener("click", async () => {
  const name = ($("#job-head").textContent || "this app").split(":")[0].trim();
  if (!confirm(`Cancel the build of ${name}? Claude stops now; files written so far stay in the folder.`)) return;
  try { await api(`/api/builds/${encodeURIComponent(JOB)}/cancel`, { method: "POST", body: "{}" }); }
  catch (e) { $("#job-meta").textContent = "Cancel failed: " + e.message; }
});
$("#launch").addEventListener("click", async () => {
  try {
    const r = await api(`/api/builds/${encodeURIComponent(JOB)}/launch`, { method: "POST", body: "{}" });
    const u = safeUrl(r.url) || (r.url && r.url.startsWith("http://127.0.0.1:") ? r.url : null);
    toast("App started" + (u ? " at " + u : ""), "play");
    $("#launch-out").replaceChildren(`Started in the sandbox (${r.health}). `, u ? extLink(u, u) : "");
    $("#launch").hidden = true; $("#stop-app").hidden = false;
  } catch (e) { $("#launch-out").textContent = "Launch failed: " + e.message; }
});
$("#stop-app").addEventListener("click", async () => {
  try {
    await api(`/api/builds/${encodeURIComponent(JOB)}/stop`, { method: "POST", body: "{}" });
    $("#launch-out").textContent = "App stopped."; $("#stop-app").hidden = true; $("#launch").hidden = false;
  } catch (e) { $("#launch-out").textContent = "Stop failed: " + e.message; }
});

async function loadBuilds() {
  try {
    const { builds } = await api("/api/builds");
    const tb = $("#bt tbody"); tb.replaceChildren();
    for (const b of builds) {
      const a = el("a", { href: "#" }, b.app_name);
      a.addEventListener("click", (e) => { e.preventDefault(); watch(b.id); });
      tb.append(el("tr", {}, whenCell(b.created_at), el("td", {}, a),
        el("td", {}, statusChip(b.status)), el("td", { class: "small" }, el("span", { class: "mono" }, b.output_dir), " ", copyBtn(b.output_dir, "Folder path")),
        el("td", { class: "small num" }, b.cost_usd != null ? "$" + b.cost_usd.toFixed(2) : "—")));
    }
    labelCells("#bt");
    if (!builds.length) messageRow(tb, 5, "List the required inputs above, then choose Create app.", "", "No builds yet", "build");
    const running = builds.find((b) => ACTIVE.has(b.status));
    if (running && !JOB) watch(running.id);
  } catch (e) { messageRow($("#bt tbody"), 5, "Could not load builds: " + e.message + ". Reload the page to retry.", "err"); }
}

/* ------------------------------------------------------------ saved analyses */
async function openAnalysis(id) {
  const status = $("#status"); status.className = "";
  try {
    const rec = await api(`/api/analyses/${encodeURIComponent(id)}`);
    $("#req").value = rec.result.requirement;
    $("#gh").checked = rec.github !== false;
    selectTab("analyze");
    render(rec.result); updateCount();
    status.textContent = `Showing the saved analysis from ${fmtTime(rec.created_at)}. Click Analyze to run it again.`;
    reveal($("#out"));
  } catch (e) { status.className = "err"; status.textContent = "Could not open: " + e.message; }
}

async function loadAnalyses() {
  try {
    const { analyses } = await api("/api/analyses");
    const tb = $("#ht tbody"); tb.replaceChildren();
    for (const h of analyses) {
      const del = el("button", { type: "button", class: "ghost danger-ic", "aria-label": "Delete analysis from " + fmtTime(h.created_at), title: "Delete" }, icon("trash"));
      del.addEventListener("click", async () => {
        if (!confirm(`Delete the saved analysis from ${fmtTime(h.created_at)} ("${h.requirement.slice(0, 60)}")? This cannot be undone.`)) return;
        try { await api(`/api/analyses/${encodeURIComponent(h.id)}/delete`, { method: "POST", body: "{}" }); loadAnalyses(); toast("Saved analysis deleted", "trash"); }
        catch (e) { $("#status").className = "err"; $("#status").textContent = "Delete failed: " + e.message; }
      });
      // UEUIS §3: never hide meaning; long requirements expand in place (keyboard and screen-reader reachable).
      // the requirement text is the "open" control: one action per row instead of two buttons
      const open = el("button", { type: "button", class: "textbtn open-link", title: h.requirement },
        h.requirement.length > 140 ? h.requirement.slice(0, 140) + "…" : h.requirement,
        el("span", { class: "sr-only" }, " (open this saved analysis)"));
      open.addEventListener("click", () => openAnalysis(h.id));
      const reqCell = open;
      tb.append(el("tr", {}, whenCell(h.created_at),
        el("td", {}, reqCell),
        el("td", { class: "small" }, h.best_name ? el("span", {}, el("strong", { class: "num" }, h.best_closeness + "%"), " " + h.best_name) : "—"),
        el("td", {}, (() => { const bb = band(h.verdict); return chip(bb.word, bb.tone, bb.icon); })()),
        el("td", {}, el("div", { class: "actions" }, del))));
    }
    labelCells("#ht");
    if (!analyses.length) messageRow(tb, 5, "Each requirement you analyze is saved here with its time, so you can open it again.", "", "No past requirements yet", "clock");
    $("#hc").textContent = analyses.length ? String(analyses.length) : "";
  } catch (e) { messageRow($("#ht tbody"), 5, "Could not load saved analyses: " + e.message + ". Reload the page to retry.", "err"); }
}
loadAnalyses();
