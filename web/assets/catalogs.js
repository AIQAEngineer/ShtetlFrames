/* Scraped catalogs hub: import discovery CSVs → shared queue, catalog-scoped table. */
let catalogQueueState = {
  offset: 0,
  limit: 100,
  status: "",
  q: "",
  source: "catalog",
  total: 0,
};
let importPollTimer = null;

const catalogPoller = new Poller(loadCatalogs, 4000);

async function loadCatalogs() {
  await Promise.all([loadCatalogStats(), loadCatalogQueuePage(), pollImportJob(true)]);
}

async function loadCatalogStats() {
  const el = $("catalogStats");
  if (!el) return;
  let data;
  try {
    data = await apiGet("/api/queue?source=catalog&limit=1");
  } catch {
    return;
  }
  el.innerHTML = `
    <div class="stat"><strong>${data.n_queue ?? 0}</strong><span>In queue</span></div>
    <div class="stat"><strong>${data.n_pending ?? 0}</strong><span>Pending</span></div>
    <div class="stat"><strong>${data.n_active ?? 0}</strong><span>Active now</span></div>
    <div class="stat"><strong>${data.n_done ?? 0}</strong><span>Done</span></div>
    <div class="stat"><strong>${data.n_error ?? 0}</strong><span>Errors</span></div>
  `;
}

function catalogQueueQuery() {
  const p = new URLSearchParams({
    offset: String(catalogQueueState.offset),
    limit: String(catalogQueueState.limit),
  });
  if (catalogQueueState.source) p.set("source", catalogQueueState.source);
  if (catalogQueueState.status) p.set("status", catalogQueueState.status);
  if (catalogQueueState.q) p.set("q", catalogQueueState.q);
  return p.toString();
}

async function loadCatalogQueuePage() {
  const el = $("catalogQueueBody");
  const meta = $("catalogQueueMeta");
  if (!el) return;
  let data;
  try {
    data = await apiGet(`/api/queue?${catalogQueueQuery()}`);
  } catch {
    el.innerHTML = `<tr><td colspan="6" class="empty-cell">Could not load queue</td></tr>`;
    return;
  }
  catalogQueueState.total = data.total || 0;
  catalogQueueState.offset = data.offset ?? catalogQueueState.offset;
  catalogQueueState.limit = data.limit ?? catalogQueueState.limit;
  const items = data.items || [];
  if (!items.length) {
    el.innerHTML = `<tr><td colspan="6" class="empty-cell">No catalog rows match — import above or loosen the filters.</td></tr>`;
  } else {
    const frag = document.createDocumentFragment();
    const tmp = document.createElement("tbody");
    tmp.innerHTML = items
      .map(
        (r) => `
      <tr>
        <td class="col-id">${r.id}</td>
        <td>${statusChip(r.status)}</td>
        <td class="col-title">
          <a href="${escapeAttr(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title || r.url)}</a>
          ${r.detail ? `<div class="row-detail">${escapeHtml(String(r.detail).slice(0, 220))}</div>` : ""}
          ${r.error ? `<div class="row-error">${escapeHtml(String(r.error).slice(0, 200))}</div>` : ""}
        </td>
        <td class="col-source">${escapeHtml(r.source || "—")}</td>
        <td class="col-year">${escapeHtml(r.year || "—")}</td>
        <td class="col-act"><button type="button" class="btn danger small delete-btn" data-url="${escapeAttr(r.url)}">Delete</button></td>
      </tr>`
      )
      .join("");
    while (tmp.firstChild) frag.appendChild(tmp.firstChild);
    el.replaceChildren(frag);
    el.querySelectorAll(".delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => deleteCatalogSource(btn.dataset.url));
    });
  }
  const pg = pagerText(catalogQueueState.offset, catalogQueueState.limit, catalogQueueState.total);
  if (meta) meta.textContent = pg.text;
  const prev = $("catalogPrev");
  const next = $("catalogNext");
  if (prev) prev.disabled = pg.prevDisabled;
  if (next) next.disabled = pg.nextDisabled;
}

async function importDiscoveries(ev) {
  ev.preventDefault();
  const msg = $("importMsg");
  const btn = $("importBtn");
  const body = {
    efg: $("importEfg")?.checked !== false,
    europeana: $("importEuropeana")?.checked !== false,
    europeana_limit: Math.max(0, Number($("importEuLimit")?.value) || 0),
  };
  if (!body.efg && !body.europeana) {
    if (msg) msg.textContent = "Pick at least one source.";
    return;
  }
  if (btn) btn.disabled = true;
  if (msg) msg.textContent = "Starting import…";
  let data;
  try {
    data = await apiPost("/api/discoveries/import", body);
  } catch {
    if (msg) msg.textContent = "Cannot reach server — is start_web.bat running?";
    if (btn) btn.disabled = false;
    return;
  }
  if (!data.ok) {
    if (msg) msg.textContent = data.error === "busy" ? "An import is already running." : (data.error || "Import failed.");
    if (btn) btn.disabled = false;
    return;
  }
  if (importPollTimer) clearInterval(importPollTimer);
  importPollTimer = setInterval(() => pollImportJob(false), 1500);
  await pollImportJob(false);
  catalogPoller.start(4000);
}

async function pollImportJob(quiet) {
  const msg = $("importMsg");
  const btn = $("importBtn");
  const prog = $("importProgress");
  const bar = $("importBar");
  const jobMsg = $("importJobMsg");
  const data = await apiGet("/api/jobs/import").catch(() => ({}));
  const j = data.job || data || {};
  const st = j.status || "";
  const running = st === "running";
  if (prog) {
    prog.hidden = !(running || st === "done" || st === "error");
    prog.className = `job-status ${st || "idle"}`;
  }
  if (bar) bar.style.width = `${Number(j.progress) || 0}%`;
  if (jobMsg) jobMsg.textContent = j.message || st || "";
  if (msg && (!quiet || running)) msg.textContent = j.message || (running ? "Importing…" : "");
  if (running) {
    if (btn) btn.disabled = true;
    return;
  }
  if (importPollTimer) {
    clearInterval(importPollTimer);
    importPollTimer = null;
  }
  if (btn) btn.disabled = false;
  if (st === "done" || st === "error") await loadCatalogQueuePage();
}

async function deleteCatalogSource(url) {
  if (!confirm("Remove from queue?")) return;
  await apiPost("/api/queue/delete", { url });
  await loadCatalogs();
}

/* —— UI wiring —— */

$("catalogQueueSearch")?.addEventListener(
  "input",
  debounce((ev) => {
    catalogQueueState.q = ev.target.value.trim();
    catalogQueueState.offset = 0;
    loadCatalogQueuePage();
  }, 250)
);

$("catalogSource")?.addEventListener("change", (ev) => {
  catalogQueueState.source = ev.target.value;
  catalogQueueState.offset = 0;
  loadCatalogQueuePage();
});

$("catalogQueueStatus")?.addEventListener("change", (ev) => {
  catalogQueueState.status = ev.target.value;
  catalogQueueState.offset = 0;
  loadCatalogQueuePage();
});

$("catalogPageSize")?.addEventListener("change", (ev) => {
  catalogQueueState.limit = Math.min(500, Math.max(25, Number(ev.target.value) || 100));
  catalogQueueState.offset = 0;
  loadCatalogQueuePage();
});

$("catalogPrev")?.addEventListener("click", () => {
  catalogQueueState.offset = Math.max(0, catalogQueueState.offset - catalogQueueState.limit);
  loadCatalogQueuePage();
});

$("catalogNext")?.addEventListener("click", () => {
  if (catalogQueueState.offset + catalogQueueState.limit < catalogQueueState.total) {
    catalogQueueState.offset += catalogQueueState.limit;
    loadCatalogQueuePage();
  }
});

$("importForm")?.addEventListener("submit", importDiscoveries);

renderNav("catalogs");
loadCatalogs();
catalogPoller.start(4000);
