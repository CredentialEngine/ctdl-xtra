/* CTDL Golden Dataset Studio: throwaway prototype frontend (vanilla JS). */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const api = (p) => fetch(p).then((r) => { if (!r.ok) throw new Error(p + " " + r.status); return r.json(); });
const fmt = (n) => (n ?? 0).toLocaleString("en-US");

const ICON = {
  approved: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="7.5" fill="#12805c"/><path d="m4.8 8.2 2.2 2.2 4.2-4.6" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  "needs work": '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="7.5" fill="#d92d20"/><path d="m5.6 5.6 4.8 4.8m0-4.8-4.8 4.8" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>',
  "in review": '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.6" fill="#fff" stroke="#98a2b3" stroke-width="1.6"/><circle cx="8" cy="8" r="2" fill="#98a2b3"/></svg>',
  signal: '<svg viewBox="0 0 16 16" fill="none"><path d="M8 2.2 14.3 13H1.7L8 2.2Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 6.5v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="11.2" r=".8" fill="currentColor"/></svg>',
  open: '<svg viewBox="0 0 16 16" fill="none"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2v-7Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>',
  correct: '<svg viewBox="0 0 16 16" fill="none"><path d="m3.5 8.5 3 3 6-7" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  wrong: '<svg viewBox="0 0 16 16" fill="none"><path d="m4.5 4.5 7 7m0-7-7 7" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  missing: '<svg viewBox="0 0 16 16" fill="none"><path d="M8 3.5v9M3.5 8h9" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  question: '<svg viewBox="0 0 16 16" fill="none"><path d="M6 6.2a2.1 2.1 0 1 1 3 1.9c-.6.3-1 .8-1 1.5v.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="8" cy="12.2" r=".9" fill="currentColor"/></svg>',
  highlight: '<svg viewBox="0 0 16 16" fill="none"><path d="m9.5 2.5 4 4-6 6H3.5v-4l6-6Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M2 14.5h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  ext: '<svg viewBox="0 0 16 16" fill="none"><path d="M9 2.5h4.5V7M13.5 2.5 7 9M12 9.5v3.5H3V4h3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  copy: '<svg viewBox="0 0 16 16" fill="none"><rect x="5" y="5" width="8.5" height="8.5" rx="1.5" stroke="currentColor" stroke-width="1.5"/><path d="M11 3V2.5h-8.5V11H3" stroke="currentColor" stroke-width="1.5"/></svg>',
  download: '<svg viewBox="0 0 16 16" fill="none"><path d="M8 2.5v8m0 0L4.8 7.3M8 10.5l3.2-3.2M2.5 13.5h11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  lock: '<svg viewBox="0 0 20 20" fill="none"><rect x="4" y="9" width="12" height="8.5" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M7 9V6.5a3 3 0 0 1 6 0V9" stroke="currentColor" stroke-width="1.6"/></svg>',
  bubble: '<svg viewBox="0 0 16 16" fill="none"><path d="M3 3.2h10a1 1 0 0 1 1 1v6.1a1 1 0 0 1-1 1H8.2L5 13.8v-2.5H3a1 1 0 0 1-1-1V4.2a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M5 6.4h6M5 8.6h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  dots: '<svg viewBox="0 0 16 16" fill="currentColor"><circle cx="3.5" cy="8" r="1.4"/><circle cx="8" cy="8" r="1.4"/><circle cx="12.5" cy="8" r="1.4"/></svg>',
  spark: '<svg viewBox="0 0 16 16" fill="none"><path d="M8 1.8 9.5 6.5 14.2 8 9.5 9.5 8 14.2 6.5 9.5 1.8 8 6.5 6.5 8 1.8Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  inst: '<svg viewBox="0 0 16 16" fill="none"><path d="M2 6.2 8 2.8l6 3.4M3 6.6h10M4 7v5M6.7 7v5M9.3 7v5M12 7v5M2.5 13.4h11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  expert: '<svg viewBox="0 0 16 16" fill="none"><circle cx="8" cy="5.5" r="2.7" stroke="currentColor" stroke-width="1.5"/><path d="M2.8 14c.6-2.6 2.7-4.2 5.2-4.2s4.6 1.6 5.2 4.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
};
const VERDICT_LABEL = { correct: "Correct", wrong: "Wrong", missing: "Missing", question: "Question" };
const KIND_LABEL = { page: "Page rule", locator: "Record locator", field: "Field rule" };
const statusPill = (s) => `<span class="pill ${s === "approved" ? "approved" : s === "needs work" ? "needs" : "review"}">${ICON[s]}${s}</span>`;
const verdictBadge = (v) => v ? `<span class="verdict ${v}">${ICON[v]}${VERDICT_LABEL[v]}</span>` : `<span class="verdict none">no verdict</span>`;
const nl = (v) => esc(v).replace(/\s*\n\s*/g, ' <span class="nl">↵</span> ');
const chip = (s) => `<span class="chip-s ${s.severity}" title="${esc(s.detail)}">${esc(s.signal)}</span>`;

const S = { catalogs: null, cat: null, rules: null, rule: null, rows: null, sel: 0, filter: null, capture: null, hlMode: false, draft: null, note: "" };
let PANE = null;

// --------------------------------------------------------------------------------------- page pane
const PANE_STYLE = `
mark.gds-hl{background:rgba(253,224,120,.92)!important;color:#111!important;border-radius:2px;box-shadow:0 0 0 1.5px rgba(245,165,36,.9);padding:0 1px;-webkit-text-fill-color:#111}
mark.gds-hl.alt{background:rgba(190,242,214,.92)!important;box-shadow:0 0 0 1.5px rgba(18,128,92,.75)}
mark.gds-hl.soft{background:rgba(253,224,120,.45)!important;box-shadow:none}
mark.gds-sel{background:rgba(190,242,214,.95)!important;color:#111!important;box-shadow:0 0 0 2px #12805c;border-radius:2px;-webkit-text-fill-color:#111}
.gds-badge{display:inline-block!important;min-width:19px;height:19px;border-radius:10px;background:#f5a524;color:#fff!important;font:700 11px/19px Inter,Arial,sans-serif!important;text-align:center;margin:0 5px 0 0;vertical-align:3px;padding:0 5px;letter-spacing:0;text-transform:none;-webkit-text-fill-color:#fff;box-shadow:0 1px 2px rgba(0,0,0,.25)}
.gds-badge.alt{background:#12805c}
.gds-el{outline:2.5px solid rgba(245,165,36,.95)!important;outline-offset:3px;border-radius:3px;background:rgba(253,224,120,.25)!important}
.gds-occ{outline:2px dashed rgba(47,84,235,.6)!important;outline-offset:5px;border-radius:4px}
.gds-found{outline:1.5px solid rgba(47,84,235,.55)!important;outline-offset:2px;border-radius:3px}
.gds-found.gds-primary{outline:2.5px solid #2f54eb!important;background:rgba(47,84,235,.06)!important}
.gds-obadge{display:inline-block!important;min-width:16px;height:16px;border-radius:8px;background:#2f54eb;color:#fff!important;font:700 9.5px/16px Inter,Arial,sans-serif!important;text-align:center;margin:0 5px 0 0;padding:0 4px;vertical-align:1px;-webkit-text-fill-color:#fff}
mark.gds-unc{background:#ffe4ea!important;color:#9f1239!important;-webkit-text-fill-color:#9f1239;border-radius:2px;box-shadow:0 0 0 2px #e11d48;text-decoration:underline wavy #e11d48;text-underline-offset:3px;padding:0 2px}
::selection{background:rgba(190,242,214,.95)}`;

class PagePane {
  constructor(el) {
    this.el = el; this.mode = "page"; this.tabs = []; this.active = null; this.hls = []; this.ctx = ""; this.onSelect = null; this.loadedStem = null;
    el.innerHTML = `<div class="browser">
      <div class="b-tabs"><div class="dots"><i></i><i></i><i></i></div><div class="tabs-in" style="display:flex;gap:2px;min-width:0;flex:1"></div></div>
      <div class="b-url"><div class="addr"></div><div class="seg"><button data-m="page" class="on">Page</button><button data-m="html">HTML</button></div><a class="ext" target="_blank" title="Open the live page">${ICON.ext}</a></div>
      <div class="b-ctx"></div>
      <div class="b-body"><iframe sandbox="allow-same-origin" referrerpolicy="no-referrer"></iframe><div class="b-loading">Loading saved page…</div><div class="b-src" hidden></div></div></div>`;
    this.iframe = $("iframe", el);
    this.iframe.addEventListener("load", () => this.onLoad());
    el.querySelectorAll(".seg button").forEach((b) => b.onclick = () => { this.mode = b.dataset.m; this.render(); });
    new ResizeObserver(() => this.fit()).observe($(".b-body", el));
  }
  set({ tabs, active, hls, ctx, ctxSel }) {
    this.tabs = tabs; this.active = active ?? (tabs[0] && tabs[0].stem); this.hls = hls || []; this.ctx = ctx || ""; this.ctxSel = ctxSel;
    this.render();
  }
  activeTab() { return this.tabs.find((t) => t.stem === this.active) || this.tabs[0]; }
  render() {
    const t = this.activeTab();
    const tabsEl = $(".tabs-in", this.el);
    tabsEl.innerHTML = this.tabs.slice(0, 3).map((tb, i) => `<div class="b-tab ${tb.stem === this.active ? "on" : ""}" data-s="${esc(tb.stem)}" title="${esc(tb.title)}">
        <span class="num ${i ? "alt" : ""}">${i + 1}</span><span class="t">${esc(tb.label || tb.title)}</span></div>`).join("") +
      (this.tabs.length > 3 ? `<div class="b-tab" style="flex:none"><span class="more">+${this.tabs.length - 3}</span></div>` : "");
    tabsEl.querySelectorAll(".b-tab[data-s]").forEach((n) => n.onclick = () => { this.active = n.dataset.s; this.render(); if (this.onTab) this.onTab(this.active); });
    $(".addr", this.el).textContent = t ? t.url : "";
    $(".ext", this.el).href = t ? t.url : "#";
    const ctx = $(".b-ctx", this.el);
    ctx.innerHTML = this.ctx; ctx.hidden = !this.ctx; ctx.classList.toggle("sel", !!this.ctxSel);
    this.el.querySelectorAll(".seg button").forEach((b) => b.classList.toggle("on", b.dataset.m === this.mode));
    const src = $(".b-src", this.el);
    if (this.mode === "html") { src.hidden = false; this.iframe.style.visibility = "hidden"; this.showSource(); }
    else { src.hidden = true; this.iframe.style.visibility = "visible"; }
    if (!t) return;
    const url = `/api/c/${S.cat}/pages/${t.stem}/render`;
    if (this.loadedStem !== t.stem) {
      this.loadedStem = t.stem; $(".b-loading", this.el).hidden = false;
      this.iframe.src = url;
    } else this.apply();
    this.fit();
  }
  fit() {
    const body = $(".b-body", this.el); const W = body.clientWidth, H = body.clientHeight;
    const LW = Math.max(W, 1024); const sc = W / LW;
    Object.assign(this.iframe.style, { width: LW + "px", height: H / sc + "px", transform: `scale(${sc})` });
  }
  doc() { try { return this.iframe.contentDocument; } catch { return null; } }
  onLoad() {
    const d = this.doc(); if (!d || !d.head) return;
    $(".b-loading", this.el).hidden = true;
    const st = d.createElement("style"); st.textContent = PANE_STYLE; d.head.appendChild(st);
    d.addEventListener("mouseup", () => this.captureSelection());
    d.addEventListener("click", (e) => { const a = e.target.closest && e.target.closest("a"); if (a) e.preventDefault(); }, true);
    this.apply();
  }
  clear(d) {
    d.querySelectorAll(".gds-badge, .gds-obadge").forEach((n) => n.remove());
    d.querySelectorAll("mark.gds-hl, mark.gds-sel, mark.gds-unc").forEach((m) => { const p = m.parentNode; while (m.firstChild) p.insertBefore(m.firstChild, m); p.removeChild(m); p.normalize(); });
    d.querySelectorAll(".gds-el, .gds-occ, .gds-found").forEach((n) => n.classList.remove("gds-el", "gds-occ", "gds-found", "gds-primary"));
  }
  apply() {
    const d = this.doc(); if (!d || !d.body || this.loadedStem !== this.active) return;
    this.clear(d);
    let primary = null;
    const t = this.activeTab();
    for (const h of this.hls.filter((h) => h.stem === t.stem)) {
      if (!h.css_path) continue;
      let el; try { el = d.querySelector(h.css_path); } catch { el = null; }
      if (!el) continue;
      if (h.found) {
        el.classList.add("gds-found"); if (h.primary) el.classList.add("gds-primary");
        const b = d.createElement("span"); b.className = "gds-obadge"; b.textContent = h.n; el.insertBefore(b, el.firstChild);
        if (h.primary) primary = primary || el; continue;
      }
      if (h.unc) { wrapText(d, el, h, "", "gds-unc"); continue; }
      if (h.occ) { el.classList.add("gds-occ"); if (h.primary) primary = primary || el; continue; }
      const marks = wrapText(d, el, h, h.cls || "");
      const badge = d.createElement("span"); badge.className = "gds-badge" + (h.cls && h.cls.includes("alt") ? " alt" : ""); badge.textContent = h.n;
      if (marks.length) marks[0].parentNode.insertBefore(badge, marks[0]); else { el.classList.add("gds-el"); el.insertBefore(badge, el.firstChild); }
      if (h.primary) primary = marks[0] || el;
    }
    let capEl = null;
    if (S.capture && S.capture.stem === t.stem) capEl = this.showCapture(d);
    const target = (S.missed && capEl) || primary;
    if (target) {
      const go = () => { target.scrollIntoView({ block: target === capEl ? "start" : "center" }); if (target === capEl) d.defaultView.scrollBy(0, -160); };
      (this.timers || []).forEach(clearTimeout);  // a newer highlight wins over pending re-scrolls
      go(); this.timers = [250, 700, 1400].map((ms) => setTimeout(go, ms));
    }
  }
  showCapture(d) {
    const c = S.capture; let el; try { el = d.querySelector(c.css_path); } catch { el = null; }
    if (el) wrapText(d, el, { char_start: c.char_start, char_end: c.char_end, raw_text: c.exact_full }, "", "gds-sel");
    return el;
  }
  captureSelection() {
    if (!S.hlMode) return;
    const d = this.doc(); const sel = d.getSelection(); if (!sel || sel.isCollapsed) return;
    const range = sel.getRangeAt(0); let el = range.commonAncestorContainer; if (el.nodeType === 3) el = el.parentElement;
    const pre = d.createRange(); pre.selectNodeContents(el); pre.setEnd(range.startContainer, range.startOffset);
    const start = pre.toString().length, exact = range.toString(), end = start + exact.length, text = el.textContent;
    S.capture = { stem: this.active, css_path: cssPathOf(el), char_start: start, char_end: end, exact_full: exact,
      prefix: text.slice(Math.max(0, start - 30), start), suffix: text.slice(end, end + 30) };
    sel.removeAllRanges();
    this.apply();
    if (this.onSelect) this.onSelect(S.capture);
  }
  async showSource() {
    const src = $(".b-src", this.el); const t = this.activeTab(); const h = this.hls.find((x) => x.primary && x.stem === t.stem);
    const occ = this.hls.find((x) => x.occ && x.stem === t.stem) || h;
    src.textContent = "Loading…";
    const r = await api(`/api/c/${S.cat}/pages/${t.stem}/source` + (occ && occ.css_path ? `?css=${encodeURIComponent(occ.css_path)}` : ""));
    let html = esc(r.html).replace(/(&lt;\/?)([a-z0-9-]+)/g, '$1<span class="tag">$2</span>').replace(/ ([a-z-]+)=(&quot;)/g, ' <span class="attr">$1</span>=$2');
    const needle = h && h.raw_text && esc(h.raw_text.trim().slice(0, 60));
    if (needle) html = html.replace(needle, `<span class="hit">${needle}</span>`);
    src.innerHTML = `<div class="faint" style="margin-bottom:8px">${esc(occ && occ.css_path || "content root")}</div>` + html;
    const hit = $(".hit", src); if (hit) hit.scrollIntoView({ block: "center" });
  }
}

function cssPathOf(el) {
  const parts = [];
  while (el && el.nodeType === 1) {
    const p = el.parentElement; const tag = el.localName;
    if (!p) { parts.push(tag); break; }
    const same = Array.from(p.children).filter((c) => c.localName === tag);
    parts.push(`${tag}:nth-of-type(${same.indexOf(el) + 1})`); el = p;
  }
  return parts.reverse().join(" > ");
}

function wrapText(d, el, h, cls, base = "gds-hl") {
  const text = el.textContent; let s = h.char_start, e = h.char_end;
  const raw = (h.raw_text || "").trim();
  if (s == null || text.slice(s, e).trim() !== raw) {
    const i = raw ? text.indexOf(raw.slice(0, 200)) : -1;
    if (i >= 0) { s = i; e = i + raw.length; }
    else if (s == null) return [];
  }
  const nodes = []; const w = d.createTreeWalker(el, NodeFilter.SHOW_TEXT); let pos = 0, n;
  while ((n = w.nextNode())) { nodes.push([n, pos, pos + n.data.length]); pos += n.data.length; }
  const marks = [];
  for (const [node, a, b] of nodes) {
    const x = Math.max(s, a), y = Math.min(e, b); if (x >= y) continue;
    if (!node.data.slice(x - a, y - a).trim()) continue;
    let target = node; if (x - a > 0) target = target.splitText(x - a); if (y - x < target.data.length) target.splitText(y - x);
    const m = d.createElement("mark"); m.className = `${base} ${cls}`.trim(); target.parentNode.insertBefore(m, target); m.appendChild(target); marks.push(m);
  }
  return marks;
}

// --------------------------------------------------------------------------------------- routing / chrome
function route() {
  const h = location.hash.replace(/^#/, "") || "/";
  const [path, qs] = h.split("?"); const p = path.split("/").filter(Boolean); const params = new URLSearchParams(qs || "");
  return { p, params };
}
window.addEventListener("hashchange", () => main());

// Who is reviewing: a list of names remembered in this browser. No login, no profiles.
const store = { get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} } };
function reviewer() { return store.get("studio.reviewer", "Jared"); }
function renderWho() {
  const names = store.get("studio.reviewers", ["Jared", "Seth", "Eric"]); const me = reviewer();
  if (!names.includes(me)) names.push(me);
  $("#who").innerHTML = `<label class="who-l">Reviewing as <select id="whosel">${names.map((n) => `<option ${n === me ? "selected" : ""}>${esc(n)}</option>`).join("")}<option value="__add">Add a name…</option></select></label>`;
  $("#whosel").onchange = (e) => {
    if (e.target.value === "__add") { const n = (prompt("Name of the reviewer") || "").trim(); if (n) { names.push(n); store.set("studio.reviewers", names); store.set("studio.reviewer", n); } }
    else store.set("studio.reviewer", e.target.value);
    renderWho();
  };
}

function chrome(tab) {
  const tabs = ["rules", "records", "compare", "prompt", "golden"];
  $("#tabs").innerHTML = S.cat ? tabs.map((t) => `<a href="#/c/${S.cat}/${t}" class="${t === tab ? "on" : ""}">${t[0].toUpperCase() + t.slice(1)}</a>`).join("") : "";
  const c = S.catalogs && S.catalogs.find((x) => x.catalog === S.cat);
  $("#crumbs").innerHTML = c ? `<span class="sep">/</span><a href="#/" class="chip crumb-cat" style="text-decoration:none">${c.logo ? `<img src="${c.logo}" alt="">` : ""}${esc(c.name)}</a>
    <span class="muted">pages saved ${fmtDate(c.crawl)}</span>` : "";
  renderWho();
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fmtDate = (crawl) => `${+crawl.slice(8, 10)} ${MONTHS[+crawl.slice(5, 7) - 1]} ${crawl.slice(0, 4)}`;
function keys(html) { $("#keys").innerHTML = html || ""; }
function toast(msg) { const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), 1800); }

async function main() {
  if (!S.catalogs) S.catalogs = await api("/api/catalogs");
  const { p, params } = route();
  if (p[0] !== "c") { S.cat = null; chrome(); keys(); return picker(); }
  S.cat = p[1]; const tab = p[2] || "rules"; chrome(tab);
  if (tab === "rules") return rulesTab(p[3], params);
  if (tab === "records") return recordsTab(p[3], params);
  if (tab === "compare") return compareTab(params);
  if (tab === "prompt") return promptTab(params);
  if (tab === "golden") return goldenTab();
}

// --------------------------------------------------------------------------------------- catalog picker
function picker() {
  keys("");
  $("#app").innerHTML = `<div class="picker"><div class="picker-in"><h1>Choose a catalog</h1>
    <div class="cat-grid">${S.catalogs.map((c) => {
      const ready = c.status === "ready";
      const pct = ready && c.rules ? Math.round(100 * c.approved / c.rules) : 0;
      const body = `<div class="cat-logo ${c.logo_dark ? "dark" : ""}">${c.logo ? `<img src="${c.logo}" alt="${esc(c.name)} logo">` : ""}</div>
        <div class="cat-main">
          <div class="cat-row1"><span class="nm">${esc(c.name)}</span><span class="pages">${fmt(c.pages)} pages saved</span></div>
          <div class="cat-row2"><div class="bar"><i style="width:${pct}%"></i></div>
            <span class="bar-t">${ready ? `${c.approved} of ${c.rules} rules approved` : "rules not run yet"}</span></div>
        </div>
        <span class="open">${ready ? "Open →" : ""}</span>`;
      return ready ? `<a class="cat ready" href="#/c/${c.catalog}/rules">${body}</a>` : `<div class="cat off">${body}</div>`;
    }).join("")}</div></div></div>`;
}

// --------------------------------------------------------------------------------------- shared: names, verdict controls
const PLAIN = {
  "course-page": ["Course pages", "Which pages are a single course's own page"],
  "program-page": ["Program pages", "Which pages describe a degree or certificate"],
  "program-page-with-courses": ["Program pages that list courses", "Which program pages name courses in their requirements"],
  "locator-course-page": ["One course per course page", "Where each course starts and ends on a course page"],
  "locator-program-requirement": ["One course per requirement line", "Where each course starts and ends on a program page"],
};
const termUrl = (t) => t ? `https://credreg.net/ctdl/terms/${t.split(":")[1]}` : null;
const where = (rid) => rid.startsWith("stub") ? "course lines on program pages" : "course pages";
function ruleName(r) {  // r: status entry from /rules (has kind, property, rule_id)
  if (r.kind === "field") return r.property + (r.rule_id.startsWith("stub") ? " · program pages" : "");
  return (PLAIN[r.rule_id] || [r.rule_id])[0];
}
const VERDICT_TEXT = { correct: "Correct", wrong: "Wrong", missing: "Missing", question: "Question for the institution", comment: "Comment" };

// Compact per-record controls: ✓ correct, ✗ wrong, and a comment bubble (a note, optionally a question for the institution).
function controls(v, author, idx, comment) {
  const talk = v === "question" ? "inst" : comment ? "on" : "";
  const by = author || (comment && comment.author);
  return `<div class="ctl3" data-i="${idx}"><div class="btns">
    <button class="cb ok ${v === "correct" ? "on" : ""}" data-v="correct" title="Correct (A)">${ICON.correct}</button>
    <button class="cb no ${v === "wrong" || v === "missing" ? "on" : ""}" data-v="wrong" title="Wrong (W): select the right text on the page">${ICON.wrong}</button>
    <button class="cb talk ${talk}" data-v="comment" title="${v === "question" ? "Question for the institution" : comment ? "Comment" : "Comment (C)"}">${ICON.bubble}</button></div>
    ${by ? `<div class="byline">${esc(by)}${v === "question" ? " · question for the institution" : ""}</div>` : ""}</div>`;
}

// Inline expansion: "wrong" asks for the right text on the page; "comment" is a note with a "question for the institution" box.
function expansion(kind, r) {
  const c = S.capture; const v = S.draft;
  if (v === "comment") {
    return `<div class="expand comment">
      <input class="note" placeholder="Comment for whoever fixes the rule" value="${esc(S.note || "")}">
      <label class="chk-expert"><input type="checkbox" class="expert" ${S.expert ? "checked" : ""}>${ICON.inst}<span><b>Question for the institution</b> · only the college can answer this (send it to them)</span></label>
      <div class="ex-btns"><button class="btn primary save">Save comment <kbd class="kb-inv">Enter</kbd></button><button class="btn cancel">Cancel</button></div></div>`;
  }
  const pick = kind === "field" ? "Select the right text on the page →" : "Optional: select text on the page that shows why →";
  return `<div class="expand wrong">
    ${c ? `<blockquote class="sel-quote">${esc(c.exact_full.length > 260 ? c.exact_full.slice(0, 140) + " … " + c.exact_full.slice(-100) : c.exact_full)}</blockquote>`
      : `<div class="pick">${ICON.highlight}<span>${pick}</span>${kind === "field" && r.status !== "found" ? `<span class="faint">(the rule found nothing here; select the value the page shows)</span>` : ""}</div>`}
    <input class="note" placeholder="Note for whoever fixes the rule (optional)" value="${esc(S.note || "")}">
    <div class="ex-btns"><button class="btn primary save">Save · wrong <kbd class="kb-inv">Enter</kbd></button><button class="btn cancel">Cancel</button></div></div>`;
}

function historyLine(r) {
  const a = r.annotation; const parts = [];
  if (r.verdict && a && a.note) parts.push(`<b>${esc(a.author)}:</b> “${esc(a.note)}”`);
  if (r.verdict && a && a.expected_text && r.verdict !== "correct") parts.push(`expected “${esc(a.expected_text.slice(0, 90))}${a.expected_text.length > 90 ? "…" : ""}”`);
  if (r.comment && r.comment.note) parts.push(`${ICON.bubble.replace("<svg", '<svg class="ib"')}<b>${esc(r.comment.author)}:</b> “${esc(r.comment.note)}”`);
  for (const s of r.signals || []) {
    if (s.signal === "fixed-since-wrong") parts.push(`<span class="good">Fixed: ${esc(a ? a.author : "")} marked the previous version wrong; this matches the text he selected.</span>`);
    if (s.signal === "previously-wrong") parts.push(`<span class="bad">Marked wrong on the previous version; the new value still differs from the expected text.</span>`);
    if (s.signal === "changed-since-correct") parts.push(`<span class="bad">Marked correct on the previous version, but the value has changed since.</span>`);
    if (s.signal === "question-for-institution" && r.verdict !== "question") parts.push(`<span class="expert-t">${ICON.inst}${s.detail === "flagged" ? "Question for the institution (no note yet)" : `Question for the institution: “${esc(s.detail)}”`}</span>`);
  }
  if (r.verdict === "question" && a && !a.note) parts.push(`<span class="expert-t">${ICON.inst}Waiting for the institution's answer</span>`);
  return parts.length ? `<div class="hist">${parts.join(" · ")}</div>` : "";
}

async function post(body) {
  const r = await fetch(`/api/c/${S.cat}/annotations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ author: reviewer(), ...body }) });
  return r.json();
}

// One place that turns a draft into an annotation: verdicts, or a comment (which becomes a "question" verdict when it is a question for the institution).
async function postDraft(target, draft, capture) {
  const expected = capture ? { text: capture.exact_full, css_path: capture.css_path, char_start: capture.char_start, char_end: capture.char_end,
    quote: { prefix: capture.prefix, exact: capture.exact_full, suffix: capture.suffix }, located_by: "highlight in the Studio" } : null;
  if (draft === "comment" && !S.expert) return post({ type: "comment", target, note: S.note || null });
  return post({ type: "verdict", verdict: draft === "comment" ? "question" : draft, target, expected, note: S.note || null });
}

// --------------------------------------------------------------------------------------- rules tab
async function rulesTab(ruleId, params) {
  const app = $("#app");
  if (!$(".rules-layout", app)) {
    app.innerHTML = `<div class="rules-layout"><aside class="col"><div class="rule-list" id="rl"></div></aside>
      <section class="col mid"><div id="rh"></div><div class="rows-bar" id="rb"></div><div class="rows" id="rows"></div><div class="hint" id="hint"></div></section>
      <section class="col pane" id="pane"></section></div>`;
    PANE = new PagePane($("#pane"));
    PANE.onSelect = () => S.missed ? renderMissed() : renderRow(S.sel);
  }
  S.rules = await api(`/api/c/${S.cat}/rules`);
  ruleId = ruleId || "course-description";
  renderRuleList(ruleId);
  const data = await api(`/api/c/${S.cat}/rules/${ruleId}/rows`);
  S.rule = data; S.rows = data.rows; S.detail = await api(`/api/c/${S.cat}/rules/${ruleId}`);
  const want = params.get("row");
  S.sel = want ? Math.max(0, S.rows.findIndex((r) => r.course_key === want || r.page_stem === want)) : 0;
  S.capture = null; S.hlMode = false; S.draft = null; S.note = ""; S.expert = false; S.missed = null;
  renderRuleHead(); renderRows(); selectRow(S.sel, true);
  keys("");
  $("#hint").innerHTML = `<kbd>Tab</kbd>next <kbd>A</kbd>correct <kbd>W</kbd>wrong <kbd>C</kbd>comment <kbd>Enter</kbd>save <kbd>Esc</kbd>cancel`;
}

function renderRuleList(active) {
  const g = S.rules.groups;
  const item = (r) => `<div class="rule-item ${r.rule_id === active ? "on" : ""}" data-r="${r.rule_id}">
      <div class="ico" title="${r.status}">${ICON[r.status]}</div>
      <div style="min-width:0"><div class="nm">${esc(ruleName(r))}</div><div class="id ${r.kind === "field" ? "" : "plain"}">${r.kind === "field" ? esc(r.ctdl || "no CTDL term") : esc((PLAIN[r.rule_id] || ["", ""])[1])}</div></div>
      <div class="meta"><span class="rev ${r.reviewed ? "" : "none"}" title="records with a verdict / all records">${fmt(r.reviewed)} / ${fmt(r.count)} reviewed</span>${r.open ? `<span class="stat open" title="records marked wrong, or with an open question for the institution">${ICON.open}${r.open}</span>` : ""}</div></div>`;
  const counts = (arr) => `${arr.filter((r) => r.status === "approved").length} of ${arr.length} approved`;
  $("#rl").innerHTML = `
    <div class="group-h"><span class="panel-title">Page rules</span><span class="sub">${counts(g.page)}</span></div>${g.page.map(item).join("")}
    <div class="group-h"><span class="panel-title">Record locators</span><span class="sub">${counts(g.locator)}</span></div>${g.locator.map(item).join("")}
    <div class="group-h"><span class="panel-title">Field rules</span><span class="sub">${counts(g.field)}</span></div>${g.field.map(item).join("")}`;
  $("#rl").querySelectorAll(".rule-item").forEach((n) => n.onclick = () => location.hash = `#/c/${S.cat}/rules/${n.dataset.r}`);
}

function defRows(rule) {
  const d = rule.definition; const out = [];
  const L = (k, v) => out.push(`<dt>${k}</dt><dd>${v}</dd>`);
  if (rule.kind === "page") {
    if (d.url_regex) L("Page address must match", `<code>${esc(d.url_regex)}</code>`);
    if (d.requires_selector) L("Page must contain", `<code>${esc(d.requires_selector)}</code> (a CSS selector)`);
    if (d.forbids_selector) L("Page must not contain", `<code>${esc(d.forbids_selector)}</code>`);
  } else if (rule.kind === "locator") {
    L("Used on", d.page_rules.map((p) => `${esc(PLAIN[p][0])} <span class="faint">(<code>${p}</code>)</span>`).join(", "));
    L("One course is", d.repeat ? `each <code>${esc(d.repeat)}</code> element` : "the whole content area of the page");
    if (d.repeat_filter) L("Kept only if its text matches", `<code>${esc(d.repeat_filter.regex)}</code>`);
  } else {
    const loc = d.locator;
    L("Looks inside", `${esc(PLAIN[loc][0].toLowerCase())} <span class="faint">(record locator <code>${loc}</code>)</span>`);
    if (d.rule_type === "constant") L("Value", `always <code>${esc(d.value)}</code>; nothing is read from the page`);
    else if (d.rule_type === "source_url") L("Value", "the page's own address");
    else {
      if (d.selector) L("Element (CSS selector)", `<code>${esc(d.selector)}</code>`);
      if (d.regex) L("Keeps the part matching", `<code>${esc(d.regex)}</code>${d.group ? ` (group ${d.group})` : ""}`);
      if (d.transforms && d.transforms.length) L("Then cleans up with", d.transforms.map((t) => `<code>${esc(t)}</code>`).join(" "));
    }
  }
  return out.join("");
}

function renderRuleHead() {
  const { rule, status } = S.rule; const det = S.detail;
  const isField = rule.kind === "field";
  const title = isField ? (rule.ctdl_property ? `<a class="term" href="${det.ctdl_url}" target="_blank" rel="noopener">${esc(rule.ctdl_property)}${ICON.ext}</a>` : `<span class="term">${esc(rule.property_label)}</span>`)
    : `<span class="term plain">${esc(PLAIN[rule.rule_id][0])}</span>`;
  const sub = isField ? `${esc(rule.property_label)}${rule.ctdl_property ? "" : " · no CTDL term"} · ${where(rule.rule_id)}` : `${esc(PLAIN[rule.rule_id][1])} · ${rule.kind === "page" ? "page rule" : "record locator"}`;
  const approved = status.status === "approved"; const block = det.blocking;
  const tip = block ? `Can't approve yet: ${block} record${block > 1 ? "s are" : " is"} marked wrong or missing. A rule is approved only when none of its records is. Fix the rule with “Improve this rule”, or change those verdicts.` : "";
  const firstVersion = rule.version === 1;
  $("#rh").innerHTML = `<div class="rule-head">
    <div class="rh-top"><div class="rh-title"><h1>${title}</h1><div class="rh-sub">${sub}</div></div>
      <a class="btn" href="#/c/${S.cat}/prompt?scope=${rule.rule_id}&from=rules">${ICON.spark}Improve this rule</a>
      <span class="tipwrap" ${tip ? `data-tip="${esc(tip)}"` : ""}><button class="btn approve" id="approve" ${approved || block ? "disabled" : ""}>${ICON.correct}${approved ? "Approved" : "Approve"}</button></span></div>
    <details class="how"><summary>How this rule works</summary>
      <dl class="wwh"><dt>What it finds</dt><dd>${esc(rule.what)}</dd><dt>How</dt><dd>${esc(rule.how)}</dd>
        <dt>Why</dt><dd class="${rule.why ? "" : "empty"}">${esc(rule.why || "Nobody has changed this rule yet: it was carried over unchanged from the previous review tool (review-ui-v2).")}</dd></dl>
      <dl class="tech">${defRows(rule)}
        ${status.fill_detail ? `<dt>Filled</dt><dd>${esc(status.fill_detail)} (${esc(status.fill)})</dd>` : `<dt>Found</dt><dd>${esc(status.fill)}</dd>`}
        ${rule.depends_on.length ? `<dt>Depends on</dt><dd>${rule.depends_on.map((d) => `${esc((PLAIN[d] || [d])[0])} <span class="faint">(<code>${d}</code>)</span>`).join(", ")}: if that rule changes, this one is run again.</dd>` : ""}
        <dt>Version</dt><dd>Version ${rule.version} of this rule${firstVersion ? " (the first)" : ""}, published by ${esc(rule.published_by)}. Earlier versions: see the Compare tab.</dd>
        <dt>Fingerprint</dt><dd><code>${esc(rule.content_hash.slice(0, 23))}…</code> · changes whenever the rule or a rule it depends on changes.</dd>
        <dt>These rows</dt><dd>Values from running the current rules (ruleset version ${S.detail.ruleset}) over the pages saved on ${esc(det.crawl_date)}; stored as extraction <code>${esc(S.rule.extraction)}</code>.</dd></dl>
    </details></div>`;
  $("#approve").onclick = async () => {
    await post({ type: "approve", target: { kind: "rule", rule_id: rule.rule_id, rule_version_seen: rule.version }, note: "Approved in the Studio" });
    toast(`Approved: ${ruleName(S.rules.groups[rule.kind].find((r) => r.rule_id === rule.rule_id))}`); main();
  };
}

const unitWord = () => ({ page: "pages", locator: "courses found", field: S.rule.rule.rule_id.startsWith("stub") ? "course lines" : "courses" }[S.rule.rule.kind]);

function renderRows() {
  const d = S.rule; const rows = S.rows;
  $("#rb").innerHTML = `<span><b>${fmt(d.total)}</b> ${unitWord()} · sorted with the likeliest problems first</span>`;
  const shown = Math.max(300, S.sel + 40);
  $("#rows").innerHTML = rows.slice(0, shown).map((r, i) => `<div class="row" data-i="${i}" tabindex="-1"></div>`).join("") +
    (rows.length > shown ? `<div class="row more-rows">+ ${fmt(rows.length - shown)} more</div>` : "");
  rows.slice(0, shown).forEach((_, i) => renderRow(i));
}

function renderRow(i) {
  const n = $(`#rows .row[data-i="${i}"]`); if (!n) return;
  const r = S.rows[i]; const kind = S.rule.rule.kind; const on = i === S.sel;
  const val = r.status === "found" ? r.value : (r.status === "no_match" ? "nothing found" : "empty");
  const code = kind === "page" ? "" : esc(r.course_key || "—");
  const main = kind === "page" ? `<div class="val">${esc(r.title)}</div><div class="pg">${esc(r.url.replace("https://", ""))}${r.status === "found" ? "" : " · <i>not matched</i>"}</div>`
    : `<div class="val ${r.status === "found" ? "" : "empty"}">${nl(val)}</div><div class="pg">${esc(r.title)}</div>`;
  const done = !!(r.verdict || r.comment);
  n.className = `row ${on ? "on" : ""} ${r.verdict ? "v-" + r.verdict : ""} ${done && !(on && S.draft) ? "done" : ""}`;
  n.innerHTML = `${kind === "page" ? "" : `<div class="code">${code}</div>`}<div class="body" ${kind === "page" ? 'style="grid-column:1 / span 2"' : ""}>${main}${historyLine(r)}${on && S.draft && S.draft !== "correct" ? expansion(kind, r) : ""}</div>
    ${controls(on && S.draft && S.draft !== "comment" ? S.draft : r.verdict, r.verdict && r.annotation && r.annotation.author, i, r.comment)}`;
  n.onclick = (e) => { if (e.target.closest(".ctl3, .expand")) return; selectRow(i); };
  wireControls(n, (v) => pickVerdict(i, v));
  wireExpansion(n, () => saveVerdict(i, S.draft), () => { S.draft = null; S.capture = null; setHl(false); renderRow(i); PANE.apply(); },
    () => { S.capture = null; setHl(true); renderRow(i); PANE.apply(); });
}

function wireControls(n, cb) {
  const box = $(".ctl3", n); if (!box) return;
  box.querySelectorAll(".cb").forEach((b) => b.onclick = (e) => { e.stopPropagation(); cb(b.dataset.v); });
}
function wireExpansion(n, save, cancel, redo) {
  const exp = $(".expand", n); if (!exp) return;
  const note = $(".note", exp); note.oninput = () => S.note = note.value;
  const ex = $(".expert", exp); if (ex) ex.onchange = () => S.expert = ex.checked;
  $(".save", exp).onclick = save; $(".cancel", exp).onclick = cancel;
  const rd = $(".redo", exp); if (rd) rd.onclick = (e) => { e.preventDefault(); redo(); };
}

function setHl(on) {
  S.hlMode = on; const r = S.rows && S.rows[S.sel];
  if (PANE && r) { PANE.ctx = paneCtx(r); PANE.ctxSel = on; PANE.render(); }
}

function pickVerdict(i, v) {
  if (i !== S.sel) selectRow(i);
  const r = S.rows[i];
  if (v === "correct") return saveVerdict(i, r.verdict === "correct" ? null : "correct");  // clicking ✓ again clears it
  S.draft = v; S.capture = null;
  S.note = v === "comment" ? ((r.comment && r.comment.note) || (r.verdict === "question" && r.annotation && r.annotation.note) || "") : "";
  S.expert = v === "comment" && r.verdict === "question";
  setHl(v === "wrong"); renderRow(i);
  const note = $(`#rows .row[data-i="${i}"] .note`); if (note && v === "comment") note.focus();
}

async function saveVerdict(i, v) {
  const r = S.rows[i]; const rule = S.rule.rule; const kind = rule.kind;
  const target = { kind: kind === "field" ? "match" : kind === "locator" ? "occurrence" : "page", rule_id: rule.rule_id, rule_version_seen: rule.version,
    extraction_seen: S.rule.extraction, occurrence_key: kind === "page" ? null : r.occurrence_key, course_key: r.course_key || null, page_stem: r.page_stem,
    value_index: kind === "field" ? r.value_index : null, value_seen: r.value };
  const c = v === "wrong" ? S.capture : null;
  if (v === null) await post({ type: "verdict", verdict: "cleared", target });
  else await postDraft(target, v, c);
  if (v === "comment" && !S.expert) r.comment = { note: S.note, author: reviewer() };
  else {
    const verdict = v === "comment" ? "question" : v;
    r.verdict = verdict; r.annotation = verdict ? { verdict, author: reviewer(), note: S.note || null, expected_text: c && c.exact_full, rule_version_seen: rule.version } : null;
  }
  const label = v === null ? "Verdict cleared" : v === "comment" ? (S.expert ? "Question for the institution saved" : "Comment saved") : VERDICT_TEXT[v];
  S.draft = null; S.capture = null; S.note = ""; S.expert = false; setHl(false);
  renderRow(i); toast(`${label} · ${r.course_key || shortTitle(r.title)}`);
  refreshStatus();
  if (v === "correct" || v === "wrong") selectRow(i + 1);
}

async function refreshStatus() {
  const id = S.rule.rule.rule_id;
  [S.rules, S.detail] = await Promise.all([api(`/api/c/${S.cat}/rules`), api(`/api/c/${S.cat}/rules/${id}`)]);
  S.rule.status = S.detail.status; renderRuleList(id); renderRuleHead();
}

const shortTitle = (t) => (t || "").replace(/ - Antelope Valley College.*$/, "").slice(0, 42);
function paneCtx(r) {
  const rule = S.rule.rule; const kind = rule.kind;
  const what = kind === "field" ? `<b>${esc(rule.property_label)}</b> · ${esc(r.course_key || "")}` : kind === "locator" ? `<b>Course</b> · ${esc(r.course_key || "")}` : `<b>${esc(PLAIN[rule.rule_id][0])}</b>`;
  const action = kind === "locator" ? `<button class="missed-btn" id="missed-btn">${ICON.missing}Add a course this rule missed</button>`
    : kind === "page" ? `<button class="missed-btn" id="missed-btn">${ICON.missing}Add a page this rule missed</button>` : "";
  const legend = `<span class="legend grow"><span class="sw-found">1</span>outlined = found by this rule <span class="sep">·</span> <span class="sw-unc">ABC 101</span>marked = looks like a course but wasn't found</span>`;
  if (S.missed && kind === "locator") return `${legend}<span class="adding">Adding a missed course…</span>`;
  if (S.missed && kind === "page") return `${ICON.highlight.replace("<svg", '<svg width="14" height="14"')}<span><b>Add a missed page</b> · find the page below; it opens here so you can check it.</span>`;
  if (S.hlMode) return `${ICON.highlight.replace("<svg", '<svg width="14" height="14"')}<span><b>Select the right text</b> on the page for ${what}: drag across it.</span>`;
  if (kind === "locator") return `${legend}${action}`;
  const tail = kind === "page" ? "the courses found on this page are outlined." : "the value found is highlighted.";
  return `<span class="gds-num">1</span><span class="grow">${what} — ${tail}</span>${action}`;
}

// "Add a course / page this rule missed": the rules that find things get a `missing` verdict.
document.addEventListener("click", (e) => {
  const b = e.target.closest && e.target.closest("#missed-btn"); if (!b || !S.rule) return;
  const kind = S.rule.rule.kind; const r = S.rows[S.sel];
  S.missed = { stem: kind === "page" && r.status !== "found" ? r.page_stem : null, query: "", results: [] };
  S.capture = null; S.note = ""; S.hlMode = kind === "locator";
  PANE.ctx = paneCtx(r); PANE.ctxSel = true; PANE.render(); renderMissed();
  if (kind === "page") searchPages("");
});
async function searchPages(qv) {
  S.missed.query = qv;
  S.missed.results = await api(`/api/c/${S.cat}/pages?query=${encodeURIComponent(qv)}&rule_id=${S.rule.rule.rule_id}`);
  renderMissed();
}
function renderMissed() {
  let p = $("#missed-panel");
  if (!S.missed) { if (p) p.remove(); return; }
  if (!p) { p = document.createElement("div"); p.id = "missed-panel"; p.className = "missed-panel"; $("#pane .browser").appendChild(p); }
  const kind = S.rule.rule.kind; const c = S.capture; const m = S.missed;
  const pageName = (stem) => { const t = PANE.tabs.find((x) => x.stem === stem); return t ? shortTitle(t.title) : stem; };
  const unc = S.uncovered || [];
  p.innerHTML = kind === "locator" ? `<div class="mp-h">${ICON.missing}<b>A course this rule missed</b><span class="faint">on ${esc(pageName(PANE.active))}</span></div>
      ${unc.length ? `<div class="mp-sub">Marked on this page — confirm one:</div><div class="mp-list">${unc.map((u, k) => {
          const m = u.detail.match(/“(.*)”/); const line = m ? m[1] : u.detail;
          const on = c && c.css_path === u.css_path;
          return `<div class="mp-item unc ${on ? "on" : ""}" data-k="${k}"><span><span class="sw-unc sm">${esc(u.detail.match(/'([^']+)'/)[1])}</span>${esc(line)}</span><span class="pickit">${on ? "selected" : "Confirm"}</span></div>`; }).join("")}</div>` : ""}
      ${c ? `<blockquote class="sel-quote">${esc(c.exact_full.slice(0, 220))}</blockquote>` : `<div class="pick">${ICON.highlight}<span>${unc.length ? "…or select any other course block on the page" : "Select the course's text on the page"} →</span></div>`}
      <input class="note" placeholder="Note (optional)" value="${esc(S.note || "")}">
      <div class="ex-btns"><button class="btn primary save" ${c ? "" : "disabled"}>Save · missing</button><button class="btn cancel">Cancel</button></div>`
    : `<div class="mp-h">${ICON.missing}<b>A page this rule missed</b></div>
      <input class="search-p" placeholder="Find a saved page by title or address" value="${esc(m.query)}">
      <div class="mp-list">${m.results.map((x) => `<div class="mp-item ${x.page_stem === m.stem ? "on" : ""}" data-s="${esc(x.page_stem)}"><span>${esc(shortTitle(x.title))}</span><span class="faint">${esc(x.url.replace(/^https:\/\/[^/]+/, ""))}${x.matched ? " · already matched" : ""}</span></div>`).join("")}</div>
      <input class="note" placeholder="Note (optional): why does this page belong?" value="${esc(S.note || "")}">
      <div class="ex-btns"><button class="btn primary save" ${m.stem ? "" : "disabled"}>Save · missing</button><button class="btn cancel">Cancel</button></div>`;
  $(".note", p).oninput = (e) => S.note = e.target.value;
  const sp = $(".search-p", p); if (sp) { sp.oninput = (e) => searchPages(e.target.value); }
  p.querySelectorAll(".mp-item.unc").forEach((n) => n.onclick = () => {
    const u = unc[+n.dataset.k]; const d = PANE.doc(); let el; try { el = d.querySelector(u.css_path); } catch { el = null; }
    if (!el) return;
    const t = el.textContent; const a0 = t.length - t.trimStart().length; const txt = t.trim();
    S.capture = { stem: PANE.active, css_path: u.css_path, char_start: a0, char_end: a0 + txt.length, exact_full: txt, prefix: "", suffix: "" };
    PANE.apply(); renderMissed();
  });
  p.querySelectorAll(".mp-item:not(.unc)").forEach((n) => n.onclick = () => {
    m.stem = n.dataset.s; const x = m.results.find((y) => y.page_stem === m.stem);
    PANE.set({ tabs: [{ stem: x.page_stem, title: x.title, url: x.url, label: shortTitle(x.title) }], active: x.page_stem, hls: [], ctx: paneCtx(S.rows[S.sel]), ctxSel: true });
    renderMissed();
  });
  $(".cancel", p).onclick = () => { S.missed = null; S.capture = null; S.hlMode = false; renderMissed(); selectRow(S.sel); };
  $(".save", p).onclick = async () => {
    const rule = S.rule.rule; const stem = kind === "locator" ? PANE.active : m.stem;
    await postDraft({ kind: kind === "locator" ? "occurrence" : "page", rule_id: rule.rule_id, rule_version_seen: rule.version, extraction_seen: S.rule.extraction,
      occurrence_key: null, course_key: null, page_stem: stem, value_index: null, value_seen: null }, "missing", kind === "locator" ? c : null);
    toast(kind === "locator" ? "Missed course saved" : "Missed page saved");
    S.missed = null; S.capture = null; S.hlMode = false; renderMissed(); refreshStatus(); selectRow(S.sel);
  };
}

async function selectRow(i, initial) {
  const rows = S.rows; if (!rows.length) return;
  const prev = S.sel; S.sel = Math.max(0, Math.min(i, rows.length - 1)); const r = rows[S.sel];
  if (prev !== S.sel) { S.capture = null; S.draft = null; S.note = ""; S.hlMode = false; S.missed = null; renderMissed(); renderRow(prev); }
  renderRow(S.sel);
  const on = $(`#rows .row[data-i="${S.sel}"]`); if (on) requestAnimationFrame(() => on.scrollIntoView({ block: initial ? "center" : "nearest" }));
  const kind = S.rule.rule.kind;
  let tabs = [{ stem: r.page_stem, title: r.title, url: r.url, label: shortTitle(r.title) }];
  if (r.course_key && kind !== "page") {
    const pages = await api(`/api/c/${S.cat}/course-pages?course_key=${encodeURIComponent(r.course_key)}&extraction=${S.rule.extraction}`);
    const seen = new Set([r.page_stem]);
    for (const p of pages) if (!seen.has(p.page_stem)) { seen.add(p.page_stem); tabs.push({ stem: p.page_stem, title: p.title, url: p.url, label: shortTitle(p.title) }); }
  }
  const hls = [];
  if (kind === "field") {
    hls.push({ stem: r.page_stem, css_path: r.css_path, char_start: r.char_start, char_end: r.char_end, raw_text: r.raw_text, n: 1, primary: true });
    hls.push({ stem: r.page_stem, css_path: r.occurrence_key.split("@")[1], occ: true });
  } else if (kind === "locator") {
    const [occs, unc] = await Promise.all([api(`/api/c/${S.cat}/pages/${r.page_stem}/occurrences?extraction=${S.rule.extraction}`),
      api(`/api/c/${S.cat}/pages/${r.page_stem}/uncovered?rule_id=${S.rule.rule.rule_id}&extraction=${S.rule.extraction}`)]);
    occs.filter((o) => o.locator_rule_id === S.rule.rule.rule_id).forEach((o, k) => hls.push({ stem: r.page_stem, css_path: o.css_path, found: true, n: k + 1, primary: o.occurrence_key === r.occurrence_key }));
    unc.forEach((u) => hls.push({ stem: r.page_stem, css_path: u.css_path, char_start: u.char_start, char_end: u.char_end, raw_text: null, unc: true }));
    S.uncovered = unc;
  } else {
    const occs = await api(`/api/c/${S.cat}/pages/${r.page_stem}/occurrences?extraction=${S.rule.extraction}`);
    occs.slice(0, 40).forEach((o, k) => hls.push({ stem: r.page_stem, css_path: o.css_path, occ: true, primary: k === 0 }));
  }
  PANE.set({ tabs, active: r.page_stem, hls, ctx: paneCtx(r), ctxSel: S.hlMode });
}

document.addEventListener("keydown", (e) => {
  if (!S.rule || !$(".rules-layout")) return;
  if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT" || e.target.tagName === "SELECT") {
    if (e.key === "Escape") e.target.blur();
    if (e.key === "Enter" && S.draft) saveVerdict(S.sel, S.draft);
    return;
  }
  if (e.key === "Tab") { e.preventDefault(); selectRow(S.sel + (e.shiftKey ? -1 : 1)); }
  if (e.key === "Escape" && S.draft) { S.draft = null; S.capture = null; setHl(false); renderRow(S.sel); }
  if (e.key === "Enter" && S.draft) saveVerdict(S.sel, S.draft);
  const k = { a: "correct", w: "wrong", c: "comment" }[e.key.toLowerCase()];
  if (k && !e.metaKey && !e.ctrlKey) pickVerdict(S.sel, k);
});


// --------------------------------------------------------------------------------------- records tab
async function recordsTab(ck, params) {
  ck = ck || "GEOG222";
  $("#app").innerHTML = `<div class="rec-layout"><aside class="col"><input class="search" id="q" placeholder="Find a course code"><div class="course-list" id="cl"></div></aside>
    <section class="col mid"><div id="rech"></div><div class="cards" id="cards"></div></section><section class="col pane" id="pane"></section></div>`;
  PANE = new PagePane($("#pane"));
  S.rule = null; keys("");
  const list = async (qv) => {
    const cs = await api(`/api/c/${S.cat}/courses?query=${encodeURIComponent(qv || "")}`);
    $("#cl").innerHTML = cs.map((c) => `<div class="course-item ${c.course_key === ck ? "on" : ""}" data-k="${c.course_key}"><span class="c">${c.course_key}${c.annotations ? '<span class="dot" title="has verdicts"></span>' : ""}</span><span class="t">${esc(c.name || "")}</span></div>`).join("");
    $("#cl").querySelectorAll(".course-item").forEach((n) => n.onclick = () => location.hash = `#/c/${S.cat}/records/${n.dataset.k}`);
    const on = $(".course-item.on", $("#cl")); if (on) on.scrollIntoView({ block: "center" });
  };
  $("#q").oninput = (e) => list(e.target.value);
  list("");
  const d = await api(`/api/c/${S.cat}/courses/${ck}`);
  const all = d.properties.flatMap((p) => p.values);
  const name = (d.properties.find((p) => p.property === "Learning Opportunity Name") || { values: [{}] }).values[0].value;
  const code = (d.properties.find((p) => p.property === "Coded Notation") || { values: [{}] }).values[0].value;
  const pages = []; for (const v of all) if (!pages.find((p) => p.stem === v.page_stem)) pages.push({ stem: v.page_stem, title: v.title, url: v.url, label: shortTitle(v.title), course: v.locator === "locator-course-page" });
  pages.sort((a, b) => b.course - a.course);
  const nProg = pages.filter((p) => !p.course).length;
  $("#rech").innerHTML = `<div class="rec-head"><h1>${esc(code || ck)} · ${esc(name || "")}</h1>
    <div class="sub">Found on ${pages.length} page${pages.length > 1 ? "s" : ""}: its course page${nProg ? ` and ${nProg} program page${nProg > 1 ? "s" : ""} that list${nProg > 1 ? "" : "s"} it` : ""}</div></div>`;
  let sel = { prop: params.get("prop") || "Description", i: 0 };
  const R = { draft: null };
  const draw = () => {
    $("#cards").innerHTML = d.properties.map((p, pi) => {
      const term = p.values[0].ctdl;
      return `<div class="card"><div class="card-h"><span class="bn">${pi + 1}</span>
        ${term ? `<a class="term sm" href="${termUrl(term)}" target="_blank" rel="noopener">${esc(term)}${ICON.ext}</a>` : `<span class="term sm plain">no CTDL term</span>`}
        <span class="lbl">${esc(p.property)}</span></div>
        <div class="vals">${p.values.map((v, vi) => {
          const on = p.property === sel.prop && vi === sel.i; const vv = on && R.draft && R.draft !== "comment" ? R.draft : v.verdict;
          return `<div class="v ${on ? "on" : ""} ${v.verdict ? "v-" + v.verdict : ""} ${(v.verdict || v.comment) && !(on && R.draft) ? "done" : ""}" data-p="${esc(p.property)}" data-i="${vi}">
            <div style="min-width:0"><div class="tx">${esc(v.status === "found" ? v.value : "(nothing found)")}</div>
              <div class="src"><span class="tag">${v.locator === "locator-course-page" ? "course page" : "program page"}</span><span>${esc(shortTitle(v.title))}</span></div>
              ${historyLine(v)}${on && R.draft && R.draft !== "correct" ? expansion("field", v) : ""}</div>
            ${controls(vv, v.verdict && v.annotation && v.annotation.author, `${pi}:${vi}`, v.comment)}</div>`;
        }).join("")}</div></div>`;
    }).join("");
    const onv = $("#cards .v.on"); if (onv && !R.draft) requestAnimationFrame(() => onv.closest(".card").scrollIntoView({ block: "start" }));
    $("#cards").querySelectorAll(".v").forEach((n) => {
      const p = n.dataset.p, vi = +n.dataset.i; const v = d.properties.find((x) => x.property === p).values[vi];
      n.onclick = (e) => { if (e.target.closest(".ctl3, .expand")) return; sel = { prop: p, i: vi }; R.draft = null; S.capture = null; draw(); show(); };
      wireControls(n, (verdict) => {
        sel = { prop: p, i: vi };
        if (verdict === "correct") return save(v, v.verdict === "correct" ? null : "correct");
        R.draft = verdict; S.draft = verdict; S.capture = null; S.hlMode = verdict === "wrong";
        S.note = verdict === "comment" ? ((v.comment && v.comment.note) || "") : ""; S.expert = verdict === "comment" && v.verdict === "question";
        draw(); show();
      });
      wireExpansion(n, () => save(v, R.draft), () => { R.draft = null; S.draft = null; S.capture = null; S.hlMode = false; draw(); show(); },
        () => { S.capture = null; S.hlMode = true; draw(); show(); });
    });
  };
  const save = async (v, verdict) => {
    const c = verdict === "wrong" ? S.capture : null;
    const target = { kind: "match", rule_id: v.rule_id, rule_version_seen: v.rule_version, extraction_seen: d.extraction, occurrence_key: v.occurrence_key,
      course_key: ck, page_stem: v.page_stem, value_index: v.value_index, value_seen: v.value };
    if (verdict === null) await post({ type: "verdict", verdict: "cleared", target }); else await postDraft(target, verdict, c);
    if (verdict === "comment" && !S.expert) v.comment = { note: S.note, author: reviewer() };
    else { const vv = verdict === "comment" ? "question" : verdict; v.verdict = vv; v.annotation = vv ? { author: reviewer(), note: S.note || null, expected_text: c && c.exact_full } : null; }
    R.draft = null; S.draft = null; S.capture = null; S.hlMode = false; S.note = ""; S.expert = false; draw(); show();
    toast(verdict ? `${VERDICT_TEXT[verdict]} saved` : "Verdict cleared");
  };
  const show = () => {
    const prop = sel.prop; const pv = d.properties.find((p) => p.property === prop).values[sel.i];
    const hls = [];
    d.properties.forEach((p, pi) => p.values.forEach((v, k) => { if (v.css_path) hls.push({ stem: v.page_stem, css_path: v.css_path, char_start: v.char_start, char_end: v.char_end, raw_text: v.raw_text, n: pi + 1, primary: p.property === prop && k === sel.i, cls: p.property === prop && k === sel.i ? "" : "alt" }); }));
    const n = d.properties.findIndex((p) => p.property === prop) + 1;
    PANE.set({ tabs: pages, active: pv.page_stem, hls, ctxSel: S.hlMode,
      ctx: S.hlMode ? `${ICON.highlight.replace("<svg", '<svg width="14" height="14"')}<span><b>Select the right text</b> on the page for ${esc(prop)}: drag across it.</span>`
        : `<span class="gds-num">${n}</span><span><b>${esc(prop)}</b> on ${esc(shortTitle(pv.title))} — numbers match the cards on the left.</span>` });
  };
  PANE.onSelect = () => draw();
  draw(); show();
  $("#cards").insertAdjacentHTML("afterend", `<div class="hint"><kbd>A</kbd>correct <kbd>W</kbd>wrong <kbd>C</kbd>comment · same verdicts as the Rules tab</div>`);
}


// --------------------------------------------------------------------------------------- compare
async function compareTab(params) {
  const scope = params.get("scope") || "all";
  const a = params.get("a"), b = params.get("b");
  const d = await api(`/api/c/${S.cat}/compare?scope=${scope}` + (a ? `&a=${a}` : "") + (b ? `&b=${b}` : ""));
  const c = d.counts; const go = (p) => { const q = new URLSearchParams({ scope, a: d.a, b: d.b, ...p }); location.hash = `#/c/${S.cat}/compare?` + q; };
  const diffHtml = (segs) => {
    if (!segs) return "";
    return `<div class="diff">${segs.map((s, i) => s.op === "eq" ? (s.text.length > 120 ? esc(i === 0 ? "" : s.text.slice(0, 50)) + `<span class="gap"> … </span>` + esc(i === segs.length - 1 ? "" : s.text.slice(-50)) : esc(s.text)) : `<${s.op}>${esc(s.text)}</${s.op}>`).join("")}</div>`;
  };
  const see = (r) => `<a class="see" href="#/c/${S.cat}/rules/${r.rule_id}?row=${encodeURIComponent(r.course_key || r.page_stem)}">See on page →</a>`;
  const recLine = (r, extra = "") => `<div class="crec"><span class="ck">${esc(r.course_key || "—")}</span><div class="cbody">${r.diff ? diffHtml(r.diff) : `<div class="diff faint one">unchanged · ${esc((r.new_value || "").slice(0, 160))}</div>`}${extra}</div>${see(r)}</div>`;
  const num = (n, label, cls) => `<span class="${n ? cls : "zero"}"><b>${fmt(n)}</b> ${label}</span>`;
  const sel = (name, val) => `<select class="vsel" data-k="${name}">${d.versions.map((v) => `<option value="${v}" ${v === val ? "selected" : ""}>ruleset v${v}</option>`).join("")}</select>`;
  const total = d.rules.reduce((t, r) => t + r.changed, 0);
  const cur = scope === "all" ? null : d.rules.find((r) => r.rule_id === scope);
  const whys = cur ? [cur] : d.rules;
  $("#app").innerHTML = `<div class="cmp-layout"><aside class="col"><div class="rule-list">
      <div class="group-h"><span class="panel-title">Rules that changed</span></div>
      <div class="rule-item ${scope === "all" ? "on" : ""}" data-s="all"><div></div><div><div class="nm">All changed rules</div></div><div class="meta"><span>${fmt(total)}</span></div></div>
      ${d.rules.map((r) => `<div class="rule-item ${scope === r.rule_id ? "on" : ""}" data-s="${r.rule_id}"><div></div><div style="min-width:0"><div class="nm mono-t">${esc(r.term)}</div><div class="id plain">${esc(r.property || "")} · v${r.from} → v${r.to}</div></div><div class="meta"><span>${fmt(r.changed)}</span></div></div>`).join("")}
      <div class="faint" style="font-size:11.5px;padding:10px 8px">Counts are records whose value changed.</div></div></aside>
    <section class="doc"><div class="doc-in">
      <div class="cmp-head"><h1>Compare ruleset versions</h1><div class="ctl"><label>From ${sel("a", d.a)}</label><span class="faint">→</span><label>To ${sel("b", d.b)}</label></div></div>
      <div class="sumline">${num(c.changed, "records changed", "")}<span class="dot">·</span>${num(c.fixed, "fixed", "good")}<span class="dot">·</span>${num(c["still wrong"], "still wrong", "bad")}<span class="dot">·</span>${num(c["newly wrong"], "newly wrong", "bad")}${c.new || c.vanished ? `<span class="dot">·</span>${num(c.new, "new", "")}<span class="dot">·</span>${num(c.vanished, "gone", "")}` : ""}</div>
      ${whys.map((r) => `<details class="why1"><summary>Why this version${d.rules.length > 1 && !cur ? ` of <span class="mono">${esc(r.term)}</span>` : ""}</summary><p>${esc(r.why || "No reason given.")}</p></details>`).join("")}
      <h2>Jared's earlier verdicts <span class="c">${d.decided.length} records</span></h2>
      <div class="clist">${d.decided.map((r) => recLine(r, r.annotation.note ? `<div class="cnote">${esc(r.annotation.author)}: “${esc(r.annotation.note)}”</div>` : "").replace('<div class="crec">', `<div class="crec cv"><span class="vb">${verdictBadge(r.annotation.verdict)}<span class="arr">→</span><span class="outcome ${r.outcome.replace(" ", "-")}">${r.outcome}</span></span>`)).join("")}</div>
      <h2>Signals <span class="c">click a signal to see the records that lost or gained it</span></h2>
      <div class="sigt">${d.signals.map((s, k) => { const x = s.after - s.before; return `<div class="sigrow" data-k="${k}"><span class="tw">▸</span><span class="sname">${esc(s.signal)}</span><span class="num">${fmt(s.before)}</span><span class="arrow">→</span><span class="num">${fmt(s.after)}</span><span class="num ${x < 0 ? "delta-down" : x > 0 ? "delta-up" : "faint"}">${x > 0 ? "+" : ""}${x || "–"}</span></div>
        <div class="sigdrill" data-k="${k}" hidden>${s.lost_total ? `<div class="dh good">− ${fmt(s.lost_total)} lost it${s.lost_total > s.lost.length ? ` (first ${s.lost.length})` : ""}</div><div class="clist">${s.lost.map((r) => recLine(r)).join("")}</div>` : ""}
          ${s.gained_total ? `<div class="dh bad">+ ${fmt(s.gained_total)} gained it</div><div class="clist">${s.gained.map((r) => recLine(r)).join("")}</div>` : ""}</div>`; }).join("")}</div>
      <h2>Sample of other changed records <span class="c">${d.sample.length} of ${fmt(d.sample_total)}, random</span></h2>
      <div class="clist">${d.sample.map((r) => recLine(r)).join("")}</div>
    </div></section></div>`;
  $("#app").querySelectorAll(".cmp-layout .rule-item").forEach((n) => n.onclick = () => go({ scope: n.dataset.s }));
  $("#app").querySelectorAll("select.vsel").forEach((n) => n.onchange = () => go({ [n.dataset.k]: n.value }));
  $("#app").querySelectorAll(".sigrow").forEach((n) => n.onclick = () => {
    const dr = $(`.sigdrill[data-k="${n.dataset.k}"]`); dr.hidden = !dr.hidden; n.classList.toggle("open", !dr.hidden);
  });
  keys("");
}


// --------------------------------------------------------------------------------------- prompt
async function promptTab(params) {
  const rules = await api(`/api/c/${S.cat}/rules`);
  const all = [...rules.groups.page, ...rules.groups.locator, ...rules.groups.field];
  const needs = all.filter((r) => r.status === "needs work");
  let scope = params.get("scope") || "course-description";
  const one = scope === "needs-work" ? "course-description" : scope;
  const text = await (await fetch(`/api/c/${S.cat}/prompt?scope=${scope}`)).text();
  const hl = esc(text).split("\n").map((l) => /^# /.test(l) ? `<span class="h1">${l}</span>` : /^## /.test(l) ? `<span class="h2">${l}</span>` : /^### /.test(l) ? `<span class="h3">${l}</span>` : l)
    .join("\n").replace(/`(golden-datasets [^`]+)`/g, '<span class="cmd">`$1`</span>').replace(/`([^`\n]+)`/g, '<span class="code">`$1`</span>');
  $("#app").innerHTML = `<div class="prompt-layout"><aside class="prompt-side">
    <h1>Prompt for Claude Code</h1>${params.get("from") === "rules" ? `<div class="prompt-from">Opened from the Rules tab with <b>${esc(one)}</b> selected.</div>` : ""}<div class="muted">Deterministic: the same annotations always give the same text. Eric pastes it into Claude Code on his laptop.</div>
    <label class="opt ${scope !== "needs-work" ? "on" : ""}" data-s="${one}&from=${params.get("from") || ""}"><div class="t">One rule</div><div class="d">Everything about one rule: definition, what/how/why, every annotation, signals.</div>
      <select id="rs">${all.map((r) => `<option value="${r.rule_id}" ${r.rule_id === one ? "selected" : ""}>${r.rule_id} v${r.version} · ${r.status}</option>`).join("")}</select></label>
    <label class="opt ${scope === "needs-work" ? "on" : ""}" data-s="needs-work"><div class="t">All rules needing work <span class="pill needs">${ICON["needs work"]}${needs.length}</span></div><div class="d">${needs.map((r) => r.rule_id).join(", ") || "none"}</div></label>
    <dl class="facts"><dt>Characters</dt><dd>${fmt(text.length)}</dd><dt>≈ tokens</dt><dd>${fmt(Math.round(text.length / 4))}</dd><dt>Raw HTML included</dt><dd>none</dd>
      <dt>Page references</dt><dd>${(text.match(/golden-datasets pages get/g) || []).length}</dd></dl>
    <div class="muted" style="font-size:12px;margin-top:18px">Claude reads pages with <span class="mono">golden-datasets pages get</span> and tests drafts with <span class="mono">golden-datasets rule try</span> before <span class="mono">golden-datasets rule publish</span>. The new version appears in the Studio when the manifest changes.</div>
  </aside><section class="prompt-main"><div class="prompt-bar"><span class="grow">Preview · <span class="mono">${esc(scope)}</span> · ruleset v${rules.ruleset}</span>
    <button class="btn" id="dl">${ICON.download}Download .md</button><button class="btn primary" id="cp">${ICON.copy}Copy prompt</button></div>
    <pre class="prompt-pre">${hl}</pre></section></div>`;
  $("#app").querySelectorAll(".opt").forEach((n) => n.onclick = (e) => { if (e.target.tagName === "SELECT") return; location.hash = `#/c/${S.cat}/prompt?scope=${n.dataset.s}`; });
  $("#rs").onchange = (e) => location.hash = `#/c/${S.cat}/prompt?scope=${e.target.value}`;
  $("#cp").onclick = async () => { try { await navigator.clipboard.writeText(text); } catch {} toast("Prompt copied"); };
  $("#dl").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" })); a.download = `golden-datasets-prompt-${scope}.md`; a.click(); };
  keys(`<span>Commands Claude uses: <span class="mono">golden-datasets rule show · rule annotations · pages get · rule try · rule publish</span></span>`);
}

// --------------------------------------------------------------------------------------- golden
async function goldenTab() {
  const d = await api(`/api/c/${S.cat}/golden`);
  const blocked = d.total - d.approved;
  const pub = d.publications[0];
  $("#app").innerHTML = `<div class="doc"><div class="doc-in">
    <h1>Publish the golden dataset</h1>
    <div class="lead">Turns extraction <span class="mono">${d.extraction}</span> (ruleset v${d.ruleset}) into a domain-only dataset plus a lineage table. Every rule version in the ruleset must be approved first.</div>
    <div class="gate blocked">${ICON.lock}<div class="grow"><b>Publishing is blocked:</b> ${blocked} of ${d.total} rules are not approved yet (${d.rules.filter((r) => r.status === "needs work").length} need work, ${d.rules.filter((r) => r.status === "in review").length} in review).</div>
      <button class="btn primary" disabled>Publish golden dataset</button></div>
    <div class="gold-grid">
      <div class="box"><h3>Rule status · ruleset v${d.ruleset}</h3>${d.rules.map((r) => `<div class="chk">${ICON[r.status]}<span><b>${esc(ruleName(r))}</b><span class="rid ${r.ctdl ? "" : "plain"}">${esc(r.ctdl || (PLAIN[r.rule_id] || ["", ""])[1] || "no CTDL term")}</span></span>${statusPill(r.status)}</div>`).join("")}</div>
      <div>
        <div class="box"><h3>What will be written</h3><div class="tree">${esc(d.target)}
├── &lt;page&gt;/                 <span class="c"># one folder per saved page with courses (${fmt(d.pages)})</span>
│   ├── &lt;page&gt;.json         <span class="c"># [{golden_id, fields: [{ctdl_property, property,</span>
│   │                       <span class="c">#   value, source_url, location}]}]</span>
│   └── &lt;page&gt;.html         <span class="c"># the page as crawled</span>
├── lineage.parquet         <span class="c"># one row per value → rule, version, occurrence, verdicts</span>
└── publication.json        <span class="c"># which extraction and ruleset, approvals</span></div>
          <div class="muted" style="font-size:12.5px;margin-top:10px;line-height:1.55">Same shape as the golden sets saved so far, plus <span class="mono">location</span> (css_path and character offsets on the page) on every value and a <span class="mono">golden_id</span> on every course. Learning Type is kept with <span class="mono">ctdl_property: null</span>. Rule ids and verdicts live only in <span class="mono">lineage.parquet</span>.</div></div>
        ${pub ? `<div class="box" style="margin-top:18px"><h3>Earlier publications</h3>
          <div class="chk" style="grid-template-columns:1fr auto"><span><b class="mono">${esc(pub.publication)}</b><br><span class="muted">${pub.courses} courses · ${pub.lineage_rows} lineage rows · ${esc(pub.extraction)} · ${esc(pub.selection)}</span></span><span class="pill review">example</span></div>
          <div class="muted" style="font-size:12px;margin-top:6px">${esc(pub.approval_gate.note)}</div></div>` : ""}
      </div></div>
  </div></div>`;
  keys(`<span><span class="mono">golden-datasets golden publish --extraction ${d.extraction}</span> does the same from the CLI</span>`);
}

main();
