/* British Pathé workspace: discover + scrape + queue. */
(() => {
  let patheQueueState = { offset: 0, limit: 100, status: "", q: "", total: 0 };
  const pathePoller = new Poller(loadPathe, 2000);

  async function loadPathe() {
    const data = await apiGet("/api/pathe/summary");
    renderPatheStats(data);
    renderPatheJobs(data);
    await loadPatheQueue();
  }

  function renderPatheStats(data) {
    const q = data.queue || {};
    const s = data.scrape || {};
    const el = $("patheStats");
    if (!el) return;
    const doneAll = Number(q.n_done ?? 0);
    const scrapeRunning =
      s.status === "running" || s.status === "done" || s.status === "error";
    const doneRun = scrapeRunning ? Number(s.completed ?? 0) : null;
    const doneLabel =
      doneRun != null
        ? `This run ${doneRun} · all-time ${doneAll}`
        : "Done (all-time)";
    const doneStrong = doneRun != null ? doneRun : doneAll;
    el.innerHTML = `
      <div class="stat"><strong>${q.n_queue ?? 0}</strong><span>In queue</span></div>
      <div class="stat"><strong>${q.n_pending ?? 0}</strong><span>Pending</span></div>
      <div class="stat"><strong>${q.n_active ?? 0}</strong><span>Active</span></div>
      <div class="stat"><strong>${doneStrong}</strong><span>${doneLabel}</span></div>
      <div class="stat"><strong>${q.n_error ?? 0}</strong><span>Errors</span></div>
    `;
  }

  function renderPatheJobs(data) {
    const d = data.discover || {};
    const s = data.scrape || {};
    const discovering = d.status === "running";
    const scraping = s.status === "running";

    const dProg = $("patheDiscoverProgress");
    const dBar = $("patheDiscoverBar");
    const dMsg = $("patheDiscoverMsg");
    if (dProg) {
      dProg.hidden = !(discovering || d.status === "done" || d.status === "error");
      if (dBar) dBar.style.width = `${Number(d.progress) || 0}%`;
      if (dMsg) dMsg.textContent = d.message || d.status || "";
      dProg.className = `job-status ${d.status || "idle"}`;
    }

    const sProg = $("patheScrapeProgress");
    const sBar = $("patheScrapeBar");
    const sMsg = $("patheScrapeMsg");
    if (sProg) {
      sProg.hidden = !(scraping || s.status === "done" || s.status === "error");
      if (sBar) sBar.style.width = `${Number(s.progress) || 0}%`;
      if (sMsg) {
        const live = (data.live || [])
          .slice(0, 4)
          .map((x) => `${(x.title || "").slice(0, 40)}: ${x.detail || x.phase || ""}`)
          .join("\n");
        sMsg.textContent = [s.message || s.status || "", live].filter(Boolean).join("\n");
      }
      sProg.className = `job-status ${s.status || "idle"}`;
    }

    const ds = $("patheDiscoverStatus");
    const ss = $("patheScrapeStatus");
    if (ds) {
      ds.textContent = discovering
        ? `${d.message || "Discovering…"} (${Math.round(d.progress || 0)}%)`
        : d.message || d.status || "Idle.";
    }
    if (ss) {
      ss.textContent = scraping
        ? s.message || "Scraping…"
        : s.message || s.status || "Idle.";
    }

    for (const id of ["patheDiscoverBtn", "patheDiscoverAllBtn"]) {
      const btn = $(id);
      if (btn) btn.disabled = discovering;
    }
    const scrapeBtn = $("patheScrapeBtn");
    if (scrapeBtn) scrapeBtn.disabled = scraping;

    if (discovering || scraping) pathePoller.start(scraping ? 1000 : 2000);
  }

  function assetIdFromUrl(url) {
    const m = String(url || "").match(/\/asset\/(\d+)/i);
    return m ? m[1] : "—";
  }

  async function loadPatheQueue() {
    const body = $("patheQueueBody");
    const meta = $("patheQueueMeta");
    if (!body) return;
    const params = new URLSearchParams({
      offset: String(patheQueueState.offset),
      limit: String(patheQueueState.limit),
    });
    if (patheQueueState.status) params.set("status", patheQueueState.status);
    if (patheQueueState.q) params.set("q", patheQueueState.q);
    let data;
    try {
      data = await apiGet("/api/pathe/queue?" + params);
    } catch {
      body.innerHTML = `<tr><td colspan="5" class="empty-cell">Could not load queue</td></tr>`;
      return;
    }
    patheQueueState.total = data.total || 0;
    const items = data.items || [];
    if (!items.length) {
      body.innerHTML = `<tr><td colspan="5" class="empty-cell">Queue empty — Discover all to begin.</td></tr>`;
    } else {
      body.innerHTML = items
        .map((r) => {
          const aid = assetIdFromUrl(r.url);
          return `
        <tr>
          <td class="col-id">${r.id}</td>
          <td>${statusChip(r.status)}</td>
          <td class="col-title">
            <a href="${escapeAttr(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title || "Asset " + aid)}</a>
            ${r.error ? `<div class="row-error">${escapeHtml(String(r.error).slice(0, 180))}</div>` : ""}
            ${r.detail ? `<div class="row-detail">${escapeHtml(String(r.detail).slice(0, 180))}</div>` : ""}
          </td>
          <td class="col-year">${escapeHtml(aid)}</td>
          <td class="col-act"></td>
        </tr>`;
        })
        .join("");
    }
    const pg = pagerText(patheQueueState.offset, patheQueueState.limit, patheQueueState.total);
    if (meta) meta.textContent = pg.text;
    const prev = $("pathePrev");
    const next = $("patheNext");
    if (prev) prev.disabled = pg.prevDisabled;
    if (next) next.disabled = pg.nextDisabled;
  }

  async function postDiscover(body) {
    const payload = {
      // Discover must not start scrape / spin a GPU fleet.
      auto_scrape: false,
      workers: Number($("patheWorkers")?.value || 8),
      ...body,
    };
    const data = await apiPost("/api/pathe/discover", payload);
    if (!data.ok) alert(data.error || "Discover failed");
    patheQueueState.offset = 0;
    await loadPathe();
  }

  $("patheDiscoverForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    await postDiscover({
      query: $("patheQuery")?.value || "",
      max_items: Number($("patheMax")?.value || 5000),
    });
  });

  $("patheDiscoverAllBtn")?.addEventListener("click", async () => {
    await postDiscover({
      all: true,
      query: "",
      max_items: Number($("patheMax")?.value || 5000),
    });
  });

  async function syncPatheClaimOrder() {
    const order = $("patheClaimOrder")?.value || "start";
    const data = await apiPost("/api/settings", { QUEUE_CLAIM_ORDER: order });
    if (data.ok === false) {
      throw new Error(data.error || `save failed (${data.status})`);
    }
    return data;
  }

  async function loadPatheClaimOrder() {
    const sel = $("patheClaimOrder");
    if (!sel) return;
    try {
      const data = await apiGet("/api/settings");
      const fields = data?.fields || [];
      const row = fields.find((f) => f.key === "QUEUE_CLAIM_ORDER");
      const v = (row?.value || data?.values?.QUEUE_CLAIM_ORDER || "start")
        .toString()
        .toLowerCase();
      sel.value = v === "end" ? "end" : "start";
    } catch (_) {
      /* keep default */
    }
  }

  function flashPatheSettingsSaved(ok, msg) {
    const el = $("patheSettingsSaved");
    if (!el) return;
    el.hidden = false;
    el.textContent = ok ? msg || "Settings saved." : msg || "Save failed.";
    el.style.color = ok ? "" : "var(--danger, #b33)";
    clearTimeout(window._patheSaveFlash);
    window._patheSaveFlash = setTimeout(() => {
      el.hidden = true;
    }, 2500);
  }

  $("patheSaveSettingsBtn")?.addEventListener("click", async () => {
    const btn = $("patheSaveSettingsBtn");
    if (btn) btn.disabled = true;
    try {
      await syncPatheClaimOrder();
      flashPatheSettingsSaved(true, "Queue order saved.");
    } catch (e) {
      flashPatheSettingsSaved(false, e?.message || "Save failed.");
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  $("patheScrapeBtn")?.addEventListener("click", async () => {
    const maxRaw = ($("patheScrapeMax")?.value || "all").trim();
    try {
      await syncPatheClaimOrder();
    } catch (_) {
      /* scrape can still start with prior setting */
    }
    const data = await apiPost("/api/pathe/scrape", {
      max_videos: maxRaw,
      workers: Number($("patheWorkers")?.value || 8),
    });
    if (!data.ok) alert(data.error || data.job?.message || "Scrape failed");
    await loadPathe();
  });

  $("patheClearBtn")?.addEventListener("click", async () => {
    if (!confirm("Clear all British Pathé rows from the queue?")) return;
    await apiPost("/api/pathe/queue/clear", {});
    patheQueueState.offset = 0;
    await loadPathe();
  });

  $("patheQueueSearch")?.addEventListener(
    "input",
    debounce((e) => {
      patheQueueState.q = e.target.value || "";
      patheQueueState.offset = 0;
      loadPatheQueue();
    }, 250)
  );

  $("patheQueueStatus")?.addEventListener("change", (e) => {
    patheQueueState.status = e.target.value || "";
    patheQueueState.offset = 0;
    loadPatheQueue();
  });

  $("pathePageSize")?.addEventListener("change", (e) => {
    patheQueueState.limit = Number(e.target.value) || 100;
    patheQueueState.offset = 0;
    loadPatheQueue();
  });

  $("pathePrev")?.addEventListener("click", () => {
    patheQueueState.offset = Math.max(0, patheQueueState.offset - patheQueueState.limit);
    loadPatheQueue();
  });
  $("patheNext")?.addEventListener("click", () => {
    patheQueueState.offset += patheQueueState.limit;
    loadPatheQueue();
  });

  renderNav("pathe");
  if ($("patheDiscoverForm") || $("patheStats")) {
    loadPatheClaimOrder();
    loadPathe();
    pathePoller.start(2000);
  }
})();
