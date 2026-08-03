/* Filmhíradók Online workspace: catalog discover + FHO-scoped scrape + queue. */
(() => {
  let fhoQueueState = { offset: 0, limit: 100, status: "", q: "", total: 0 };
  const fhoPoller = new Poller(loadFho, 2000);

  async function loadFho() {
    let data;
    try {
      data = await apiGet("/api/fho/summary");
    } catch {
      return;
    }
    renderFhoStats(data);
    renderFhoJobs(data);
    const bl = $("fhoBackendLabel");
    if (bl) bl.textContent = data.backend || "—";
    await loadFhoQueue();
  }

  function renderFhoStats(data) {
    const q = data.queue || {};
    const s = data.scrape || {};
    const el = $("fhoStats");
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

  function renderFhoJobs(data) {
    const d = data.discover || {};
    const s = data.scrape || {};
    const discovering = d.status === "running";
    const scraping = s.status === "running";

    const dProg = $("fhoDiscoverProgress");
    const dBar = $("fhoDiscoverBar");
    const dMsg = $("fhoDiscoverMsg");
    if (dProg) {
      dProg.hidden = !(discovering || d.status === "done" || d.status === "error");
      if (dBar) dBar.style.width = `${Number(d.progress) || 0}%`;
      if (dMsg) dMsg.textContent = d.message || d.error || d.status || "";
      dProg.className = `job-status ${d.status || "idle"}`;
    }
    const ds = $("fhoDiscoverStatus");
    if (ds) {
      ds.textContent = discovering
        ? `${d.message || "Discovering…"} (${Math.round(d.progress || 0)}%)`
        : d.message || d.status || "Idle.";
    }

    const sProg = $("fhoScrapeProgress");
    const sBar = $("fhoScrapeBar");
    const sMsg = $("fhoScrapeMsg");
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
    const ss = $("fhoScrapeStatus");
    if (ss) {
      ss.textContent = scraping ? s.message || "Scraping…" : s.message || s.status || "Idle.";
    }

    fhoPoller.start(discovering || scraping ? 1000 : 2500);
  }

  function fhoQueueQuery() {
    const p = new URLSearchParams({
      offset: String(fhoQueueState.offset),
      limit: String(fhoQueueState.limit),
    });
    if (fhoQueueState.status) p.set("status", fhoQueueState.status);
    if (fhoQueueState.q) p.set("q", fhoQueueState.q);
    return p.toString();
  }

  async function loadFhoQueue() {
    const el = $("fhoQueueBody");
    const meta = $("fhoQueueMeta");
    if (!el) return;
    let data;
    try {
      data = await apiGet(`/api/fho/queue?${fhoQueueQuery()}`);
    } catch {
      el.innerHTML = `<tr><td colspan="6" class="empty-cell">Could not load queue</td></tr>`;
      return;
    }
    fhoQueueState.total = data.total || 0;
    fhoQueueState.offset = data.offset ?? fhoQueueState.offset;
    fhoQueueState.limit = data.limit ?? fhoQueueState.limit;
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = `<tr><td colspan="6" class="empty-cell">No FHO rows match — discover above or loosen filters.</td></tr>`;
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
        btn.addEventListener("click", () => deleteFhoRow(btn.dataset.url));
      });
    }
    const pg = pagerText(fhoQueueState.offset, fhoQueueState.limit, fhoQueueState.total);
    if (meta) meta.textContent = pg.text;
    const prev = $("fhoPrev");
    const next = $("fhoNext");
    if (prev) prev.disabled = pg.prevDisabled;
    if (next) next.disabled = pg.nextDisabled;
  }

  async function deleteFhoRow(url) {
    if (!url || !confirm("Remove this FHO row from the queue?")) return;
    await apiPost("/api/queue/delete", { url });
    await loadFho();
  }

  async function discoverFho() {
    const query = ($("fhoQuery")?.value || "").trim();
    const maxPages = Number($("fhoMaxPages")?.value || 0) || 0;
    const btn = $("fhoDiscoverBtn");
    if (btn) btn.disabled = true;
    try {
      const res = await apiPost("/api/fho/discover", { query, max_pages: maxPages });
      if (!res.ok && res.error === "busy") {
        alert("Discover already running.");
      }
    } catch (e) {
      alert(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
      await loadFho();
    }
  }

  async function stopDiscoverFho() {
    try {
      await apiPost("/api/fho/discover/stop", {});
    } catch (e) {
      alert(String(e.message || e));
    }
    await loadFho();
  }

  async function startFhoScrape() {
    const max = ($("fhoScrapeMax")?.value || "all").trim() || "all";
    const workers = Number($("fhoWorkers")?.value || 4);
    const btn = $("fhoScrapeBtn");
    if (btn) btn.disabled = true;
    try {
      const res = await apiPost("/api/fho/scrape", { max_videos: max, workers });
      if (!res.ok) {
        alert(res.error === "busy" ? "Scrape already running." : res.error || "Could not start");
      }
    } catch (e) {
      alert(String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
      await loadFho();
    }
  }

  async function stopFhoScrape() {
    try {
      await apiPost("/api/fho/scrape/stop", {});
    } catch (e) {
      alert(String(e.message || e));
    }
    await loadFho();
  }

  async function clearFhoQueue() {
    if (!confirm("Delete all Filmhíradók rows from the queue?")) return;
    await apiPost("/api/fho/queue/clear", {});
    fhoQueueState.offset = 0;
    await loadFho();
  }

  function wire() {
    $("fhoDiscoverBtn")?.addEventListener("click", discoverFho);
    $("fhoDiscoverStopBtn")?.addEventListener("click", stopDiscoverFho);
    $("fhoScrapeBtn")?.addEventListener("click", startFhoScrape);
    $("fhoStopBtn")?.addEventListener("click", stopFhoScrape);
    $("fhoClearBtn")?.addEventListener("click", clearFhoQueue);
    $("fhoQueueSearch")?.addEventListener(
      "input",
      debounce(() => {
        fhoQueueState.q = $("fhoQueueSearch").value.trim();
        fhoQueueState.offset = 0;
        loadFhoQueue();
      }, 300)
    );
    $("fhoQueueStatus")?.addEventListener("change", () => {
      fhoQueueState.status = $("fhoQueueStatus").value;
      fhoQueueState.offset = 0;
      loadFhoQueue();
    });
    $("fhoPageSize")?.addEventListener("change", () => {
      fhoQueueState.limit = Number($("fhoPageSize").value) || 100;
      fhoQueueState.offset = 0;
      loadFhoQueue();
    });
    $("fhoPrev")?.addEventListener("click", () => {
      fhoQueueState.offset = Math.max(0, fhoQueueState.offset - fhoQueueState.limit);
      loadFhoQueue();
    });
    $("fhoNext")?.addEventListener("click", () => {
      fhoQueueState.offset += fhoQueueState.limit;
      loadFhoQueue();
    });
  }

  renderNav("fho");
  wire();
  loadFho();
  fhoPoller.start();
})();
