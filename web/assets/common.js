/* Shared helpers for every ShtetlFrames hub. Loaded before page scripts. */

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replaceAll("'", "&#39;");
}

/* m:ss from seconds (whole). */
function fmtTime(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

/* m:ss.ff from seconds (centisecond precision, for frame marks). */
function fmtTimeFrac(sec) {
  const n = Math.max(0, Number(sec) || 0);
  const s = Math.floor(n);
  const frac = Math.round((n - s) * 100);
  const m = Math.floor(s / 60);
  const r = s % 60;
  const base = `${m}:${String(r).padStart(2, "0")}`;
  return frac ? `${base}.${String(frac).padStart(2, "0")}` : base;
}

function fmtBytes(n) {
  const b = Number(n) || 0;
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(2)} MB`;
}

/* Wall-clock time from unix seconds. */
function fmtTs(sec) {
  const n = Number(sec);
  if (!Number.isFinite(n) || n <= 0) return "—";
  try {
    return new Date(n * 1000).toLocaleTimeString();
  } catch {
    return "—";
  }
}

async function apiGet(url) {
  const res = await fetch(url);
  return res.json();
}

/* POST JSON; always resolves to an object with ok/status so callers can branch once. */
async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  const data = await res.json().catch(() => ({}));
  if (data && typeof data === "object") {
    if (data.ok == null) data.ok = res.ok;
    data.status = res.status;
  }
  return data;
}

function debounce(fn, ms) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

/* Re-startable interval with adaptive rate. */
class Poller {
  constructor(fn, ms) {
    this.fn = fn;
    this.ms = ms;
    this.t = null;
  }
  start(ms) {
    if (ms != null) this.ms = ms;
    if (this.t && this.ms === this._activeMs) return;
    this.stop();
    this._activeMs = this.ms;
    this.t = setInterval(this.fn, this.ms);
  }
  stop() {
    if (this.t) clearInterval(this.t);
    this.t = null;
    this._activeMs = null;
  }
  get running() {
    return this.t != null;
  }
}

/* "Showing X–Y of Z" text + prev/next disabled flags for offset/limit paging. */
function pagerText(offset, limit, total) {
  const start = total ? offset + 1 : 0;
  const end = Math.min(offset + limit, total);
  return {
    start,
    end,
    text: total
      ? `Showing ${start.toLocaleString()}–${end.toLocaleString()} of ${total.toLocaleString()}`
      : "0 discovered",
    prevDisabled: offset <= 0,
    nextDisabled: offset + limit >= total,
  };
}

/* Queue-status chip (scan queue tables). */
function statusChip(status) {
  const s = status || "pending";
  return `<span class="badge queue-${escapeAttr(s)}">${escapeHtml(s)}</span>`;
}

/* Toggle .active on the chip whose data-<attr> matches value. */
function setChipGroup(rowId, attr, value) {
  document.querySelectorAll(`#${rowId} .chip`).forEach((btn) => {
    btn.classList.toggle("active", btn.dataset[attr] === value);
  });
}

/* One canonical nav — active: "scan" | "review" | "train" | "tools" | "pathe" | "catalogs". */
const NAV_LINKS = [
  ["scan", "/", "Scan"],
  ["review", "/review", "Review"],
  ["train", "/train", "Train"],
  ["tools", "/tools", "Tools"],
];

function renderNav(active) {
  const el = document.getElementById("siteNav");
  if (!el) return;
  el.className = "site-nav";
  el.innerHTML = `
    <div class="nav-left">
      <a class="brand-mark" href="/">Shtetl<span>Frames</span></a>
      <a class="nav-pathe${active === "pathe" ? " active" : ""}" href="/pathe">British Pathé</a>
      <a class="nav-pathe${active === "efg" ? " active" : ""}" href="/efg">EFG</a>
      <a class="nav-pathe${active === "catalogs" ? " active" : ""}" href="/catalogs">Catalogs</a>
    </div>
    <div class="nav-links">
      ${NAV_LINKS.map(
        ([key, href, label]) =>
          `<a${key === active ? ' class="active"' : ""} href="${href}">${label}</a>`
      ).join("")}
    </div>`;
}

/* Hub tabs: buttons .tabs [data-tab], panes .tab-pane[data-tab]; ?tab= selects on load. */
function initTabs(defaultTab, onTab) {
  const btns = [...document.querySelectorAll(".tabs [data-tab]")];
  const panes = [...document.querySelectorAll(".tab-pane[data-tab]")];
  if (!btns.length) return { select: () => {} };
  function select(tab, push = true) {
    btns.forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    panes.forEach((p) => {
      p.hidden = p.dataset.tab !== tab;
    });
    if (push) {
      const url = tab === defaultTab ? location.pathname : `?tab=${tab}`;
      history.replaceState(null, "", url);
    }
    if (onTab) onTab(tab);
  }
  btns.forEach((b) => b.addEventListener("click", () => select(b.dataset.tab)));
  const wanted = new URLSearchParams(location.search).get("tab");
  select(btns.some((b) => b.dataset.tab === wanted) ? wanted : defaultTab, false);
  return { select };
}
