/* EFG downloads workspace: import + park + EFG-scoped scrape + host monitor. */
(() => {
  let efgQueueState = { offset: 0, limit: 100, status: "", q: "", total: 0 };
  const efgPoller = new Poller(loadEfg, 2000);

  async function loadEfg() {
    let data;
    try {
      data = await apiGet("/api/efg/summary?hosts=30");
    } catch {
      return;
    }
    renderEfgStats(data);
    renderEfgJobs(data);
    renderEfgHosts(data.hosts || []);
    renderEfgKinds(data.kinds || []);
    const bl = $("efgBackendLabel");
    if (bl) bl.textContent = data.backend || "—";
    await loadEfgQueue();
  }

  function renderEfgStats(data) {
    const q = data.queue || {};
    const s = data.scrape || {};
    const el = $("efgStats");
    if (!el) return;
    const doneAll = Number(q.n_done ?? 0);
    const scrapeRunning =
      s.status === "running" || s.status === "done" || s.status === "error";
    const doneRun = scrapeRunning ? Number(s.completed ?? 0) : null;
    const doneLabel =
      doneRun != null ? `This run ${doneRun} · all-time ${doneAll}` : "Done (all-time)";
    const doneStrong = doneRun != null ? doneRun : doneAll;
    el.innerHTML = `
      <div class="stat"><strong>${q.n_queue ?? 0}</strong><span>In queue</span></div>
      <div class="stat"><strong>${q.n_pending ?? 0}</strong><span>Pending</span></div>
      <div class="stat"><strong>${q.n_active ?? 0}</strong><span>Active</span></div>
      <div class="stat"><strong>${doneStrong}</strong><span>${doneLabel}</span></div>
      <div class="stat"><strong>${q.n_error ?? 0}</strong><span>Errors</span></div>
    `;
  }

  function renderEfgJobs(data) {
    const s = data.scrape || {};
    const imp = data.import || {};
    const scraping = s.status === "running";
    const importing = imp.status === "running";

    const iProg = $("efgImportProgress");
    const iBar = $("efgImportBar");
    const iMsg = $("efgImportMsg");
    if (iProg) {
      iProg.hidden = !(importing || imp.status === "done" || imp.status === "error");
      if (iBar) iBar.style.width = `${Number(imp.progress) || 0}%`;
      if (iMsg) iMsg.textContent = imp.message || imp.error || imp.status || "";
      iProg.className = `job-status ${imp.status || "idle"}`;
    }
    const ps = $("efgPrepareStatus");
    if (ps) {
      ps.textContent = importing
        ? `${imp.message || "Working…"} (${Math.round(imp.progress || 0)}%)`
        : imp.message || imp.status || "Idle.";
    }

    const sProg = $("efgScrapeProgress");
    const sBar = $("efgScrapeBar");
    const sMsg = $("efgScrapeMsg");
    if (sProg) {
      sProg.hidden = !(scraping || s.status === "done" || s.status === "error" || s.status === "idle");
      if (s.status === "idle" && !(s.message || "").includes("stop")) sProg.hidden = true;
      if (sBar) sBar.style.width = `${Number(s.progress) || 0}%`;
      if (sMsg) {
        const live = (data.live || [])
          .slice(0, 6)
          .map((x) => `${(x.title || "").slice(0, 42)}: ${x.detail || x.phase || ""}`)
          .join("\n");
        sMsg.textContent = [s.message || s.status || "", live].filter(Boolean).join("\n");
      }
      sProg.className = `job-status ${s.status || "idle"}`;
    }
    const ss = $("efgScrapeStatus");
    if (ss) {
      ss.textContent = scraping
        ? s.message || "Scraping…"
        : s.message || s.status || "Idle.";
    }

    efgPoller.setInterval(scraping || importing ? 1000 : 2500);
  }

  function renderEfgHosts(hosts) {
    const el = $("efgHostsBody");
    if (!el) return;
    if (!hosts.length) {
      el.innerHTML = `<tr><td colspan="6" class="empty-cell">No EFG rows yet — import above.</td></tr>`;
      return;
    }
    el.innerHTML = hosts
      .map(
        (h) => `
      <tr>
        <td class="col-title">${escapeHtml(h.host || "?")}</td>
        <td>${h.pending ?? 0}</td>
        <td>${h.active ?? 0}</td>
        <td>${h.done ?? 0}</td>
        <td>${h.error ?? 0}</td>
        <td>${h.total ?? 0}</td>
      </tr>`
      )
      .join("");
  }

  function renderEfgKinds(kinds) {
    const el = $("efgKindsBody");
    if (!el) return;
    if (!kinds.length) {
      el.innerHTML = `<tr><td colspan="5" class="empty-cell">No EFG kinds yet.</td></tr>`;
      return;
    }
    el.innerHTML = kinds
      .map(
        (k) => `
      <tr>
        <td>${escapeHtml(k.kind || "efg")}</td>
        <td>${k.pending ?? 0}</td>
        <td>${k.done ?? 0}</td>
        <td>${k.error ?? 0}</td>
        <td>${k.total ?? 0}</td>
      </tr>`
      )
      .join("");
  }

  function efgQueueQuery() {
    const p = new URLSearchParams({
      offset: String(efgQueueState.offset),
      limit: String(efgQueueState.limit),
    });
    if (efgQueueState.status) p.set("status", efgQueueState.status);
    if (efgQueueState.q) p.set("q", efgQueueState.q);
    return p.toString();
  }

  async function loadEfgQueue() {
    const el = $("efgQueueBody");
    const meta = $("efgQueueMeta");
    if (!el) return;
    let data;
    try {
      data = await apiGet(`/api/efg/queue?${efgQueueQuery()}`);
    } catch {
      el.innerHTML = `<tr><td colspan="6" class="empty-cell">Could not load queue</td></tr>`;
      return;
    }
    efgQueueState.total = data.total || 0;
    efgQueueState.offset = data.offset ?? efgQueueState.offset;
    efgQueueState.limit = data.limit ?? efgQueueState.limit;
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = `<tr><td colspan="6" class="empty-cell">No EFG rows match — import above or loosen filters.</td></tr>`;
    } else {
      el.innerHTML = items
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
      el.querySelectorAll(".delete-btn").forEach((btn) => {
        btn.addEventListener("click", () => deleteEfgRow(btn.dataset.url));
      });
    }
    const pg = pagerText(efgQueueState.offset, efgQueueState.limit, efgQueueState.total);
    if (meta) meta.textContent = pg.text;
    const prev = $("efgPrev");
    const next = $("efgNext");
    if (prev) prev.disabled = pg.prevDisabled;
    if (next) next.disabled = pg.nextDisabled;
  }

  async function deleteEfgRow(url) {
    if (!url || !confirm("Remove this EFG row from the queue?")) return;
    await apiPost("/api/queue/delete", { url });
    await loadEfg();
  }

  async function importEfg() {
    const btn = $("efgImportBtn");
    if (btn) btn.disabled = true;
    try {
      const res = await apiPost("/api/efg/import", {});
      if (!res.ok && res.error === "busy") {
        alert("Import already running.");
      }
    } catch (e) {
      alert(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
      await loadEfg();
    }
  }

  async function rewriteEfg() {
    if (!confirm("Rewrite dead CDNs → YouTube offline, then re-import EFG CSV?")) return;
    const btn = $("efgRewriteBtn");
    if (btn) btn.disabled = true;
    try {
      await apiPost("/api/efg/rewrite", { import: true });
    } catch (e) {
      alert(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
      await loadEfg();
    }
  }

  async function parkEfg() {
    const btn = $("efgParkBtn");
    if (btn) btn.disabled = true;
    try {
      const res = await apiPost("/api/efg/park", {});
      alert(`Parked ${res.parked ?? 0} dead-host rows.`);
    } catch (e) {
      alert(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
      await loadEfg();
    }
  }

  async function startEfgScrape() {
    const max = ($("efgScrapeMax")?.value || "all").trim() || "all";
    const workers = Number($("efgWorkers")?.value || 4);
    const btn = $("efgScrapeBtn");
    if (btn) btn.disabled = true;
    try {
      const res = await apiPost("/api/efg/scrape", { max_videos: max, workers });
      if (!res.ok) {
        alert(res.error === "busy" ? "Scrape already running." : res.error || "Could not start");
      }
    } catch (e) {
      alert(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
      await loadEfg();
    }
  }

  async function stopEfgScrape() {
    try {
      await apiPost("/api/efg/scrape/stop", {});
    } catch (e) {
      alert(String(e.message || e));
    }
    await loadEfg();
  }

  async function clearEfgQueue() {
    if (!confirm("Delete all EFG rows from the queue?")) return;
    await apiPost("/api/efg/queue/clear", {});
    efgQueueState.offset = 0;
    await loadEfg();
  }

  function wire() {
    $("efgImportBtn")?.addEventListener("click", importEfg);
    $("efgRewriteBtn")?.addEventListener("click", rewriteEfg);
    $("efgParkBtn")?.addEventListener("click", parkEfg);
    $("efgScrapeBtn")?.addEventListener("click", startEfgScrape);
    $("efgStopBtn")?.addEventListener("click", stopEfgScrape);
    $("efgClearBtn")?.addEventListener("click", clearEfgQueue);
    $("efgQueueSearch")?.addEventListener(
      "input",
      debounce(() => {
        efgQueueState.q = $("efgQueueSearch").value.trim();
        efgQueueState.offset = 0;
        loadEfgQueue();
      }, 300)
    );
    $("efgQueueStatus")?.addEventListener("change", () => {
      efgQueueState.status = $("efgQueueStatus").value;
      efgQueueState.offset = 0;
      loadEfgQueue();
    });
    $("efgPageSize")?.addEventListener("change", () => {
      efgQueueState.limit = Number($("efgPageSize").value) || 100;
      efgQueueState.offset = 0;
      loadEfgQueue();
    });
    $("efgPrev")?.addEventListener("click", () => {
      efgQueueState.offset = Math.max(0, efgQueueState.offset - efgQueueState.limit);
      loadEfgQueue();
    });
    $("efgNext")?.addEventListener("click", () => {
      efgQueueState.offset += efgQueueState.limit;
      loadEfgQueue();
    });
  }

  renderNav("efg");
  wire();
  loadEfg();
  efgPoller.start();
})();
