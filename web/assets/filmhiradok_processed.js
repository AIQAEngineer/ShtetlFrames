/* Filmhíradók processed view: every scraped segment with a link to its source watch page. */
(() => {
  let state = { offset: 0, limit: 100, status: "done", q: "", total: 0 };
  const poller = new Poller(loadAll, 5000);

  function query() {
    const p = new URLSearchParams({
      offset: String(state.offset),
      limit: String(state.limit),
    });
    if (state.status) p.set("status", state.status);
    if (state.q) p.set("q", state.q);
    return p.toString();
  }

  async function loadAll() {
    let summary;
    try {
      summary = await apiGet("/api/fho/summary");
    } catch {
      return;
    }
    renderStats(summary);
    await loadRows();
  }

  function renderStats(data) {
    const q = data.queue || {};
    const s = data.scrape || {};
    const el = $("fhoProcStats");
    if (!el) return;
    const done = Number(q.n_done ?? 0);
    const total = Number(q.n_queue ?? 0);
    const pct = total ? ((100 * done) / total).toFixed(1) : "0.0";
    const hits = s.status === "running" || s.status === "done" ? Number(s.hits ?? 0) : 0;
    el.innerHTML = `
      <div class="stat"><strong>${done}</strong><span>Processed</span></div>
      <div class="stat"><strong>${pct}%</strong><span>Of catalog (${total})</span></div>
      <div class="stat"><strong>${hits}</strong><span>Hits this run</span></div>
      <div class="stat"><strong>${q.n_error ?? 0}</strong><span>Errors</span></div>
      <div class="stat"><strong>${q.n_active ?? 0}</strong><span>Active now</span></div>
    `;
    poller.start(s.status === "running" ? 5000 : 15000);
  }

  function resultCell(r) {
    const detail = String(r.detail || "");
    const m = detail.match(/(\d+)\s+hit segment/);
    if (m) {
      const n = Number(m[1]);
      if (n > 0) return `<span class="badge queue-done">${n} hit${n === 1 ? "" : "s"}</span>`;
      return `<span class="row-detail">no hits</span>`;
    }
    if (r.error) return `<span class="row-error">${escapeHtml(String(r.error).slice(0, 160))}</span>`;
    return detail ? `<span class="row-detail">${escapeHtml(detail.slice(0, 160))}</span>` : "—";
  }

  async function loadRows() {
    const el = $("fhoProcBody");
    const meta = $("fhoProcMeta");
    if (!el) return;
    let data;
    try {
      data = await apiGet(`/api/fho/queue?${query()}`);
    } catch {
      el.innerHTML = `<tr><td colspan="6" class="empty-cell">Could not load — is the server running?</td></tr>`;
      return;
    }
    state.total = data.total || 0;
    state.offset = data.offset ?? state.offset;
    state.limit = data.limit ?? state.limit;
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = `<tr><td colspan="6" class="empty-cell">Nothing processed yet — start the scrape on the workspace page.</td></tr>`;
    } else {
      el.innerHTML = items
        .map(
          (r) => `
        <tr>
          <td class="col-id">${r.id}</td>
          <td>${statusChip(r.status)}</td>
          <td class="col-title">
            <a href="${escapeAttr(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title || r.url)}</a>
          </td>
          <td class="col-year">${escapeHtml(r.year || "—")}</td>
          <td>${resultCell(r)}</td>
          <td class="col-source"><a href="${escapeAttr(r.url)}" target="_blank" rel="noopener">watch.php&nbsp;↗</a></td>
        </tr>`
        )
        .join("");
    }
    const pg = pagerText(state.offset, state.limit, state.total);
    if (meta) meta.textContent = pg.text;
    const prev = $("fhoProcPrev");
    const next = $("fhoProcNext");
    if (prev) prev.disabled = pg.prevDisabled;
    if (next) next.disabled = pg.nextDisabled;
  }

  function wire() {
    $("fhoProcSearch")?.addEventListener(
      "input",
      debounce(() => {
        state.q = $("fhoProcSearch").value.trim();
        state.offset = 0;
        loadRows();
      }, 300)
    );
    $("fhoProcStatus")?.addEventListener("change", () => {
      state.status = $("fhoProcStatus").value;
      state.offset = 0;
      loadRows();
    });
    $("fhoProcPageSize")?.addEventListener("change", () => {
      state.limit = Number($("fhoProcPageSize").value) || 100;
      state.offset = 0;
      loadRows();
    });
    $("fhoProcPrev")?.addEventListener("click", () => {
      state.offset = Math.max(0, state.offset - state.limit);
      loadRows();
    });
    $("fhoProcNext")?.addEventListener("click", () => {
      state.offset += state.limit;
      loadRows();
    });
  }

  renderNav("fho");
  wire();
  loadAll();
  poller.start();
})();
