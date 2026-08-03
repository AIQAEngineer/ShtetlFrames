/* SWA still-image discover + local CLIP scrape. */
(() => {
  let queueOffset = 0;
  const poller = new Poller(loadSwa, 2000);

  async function loadSwa() {
    let data;
    try {
      data = await apiGet("/api/swa/summary");
    } catch {
      return;
    }
    renderStats(data.queue || {});
    renderDiscover(data.discover || {});
    renderScrape(data.scrape || {}, data.live || []);
    await loadQueue();
  }

  function renderStats(q) {
    const el = $("swaStats");
    if (!el) return;
    el.innerHTML = [
      ["In queue", q.n_queue],
      ["Pending", q.n_pending],
      ["Active", q.n_active],
      ["Done", q.n_done],
      ["Errors", q.n_error],
    ]
      .map(
        ([label, n]) =>
          `<div class="stat"><strong>${escapeHtml(n ?? "—")}</strong><span>${label}</span></div>`
      )
      .join("");
  }

  function renderDiscover(job) {
    const box = $("swaDiscoverProgress");
    const bar = $("swaDiscoverBar");
    const msg = $("swaDiscoverMsg");
    const st = $("swaDiscoverStatus");
    const running = job.status === "running";
    if (box) box.hidden = !job.status || job.status === "idle";
    if (bar) bar.style.width = `${Math.max(0, Math.min(100, Number(job.progress) || 0))}%`;
    if (msg) msg.textContent = job.message || job.error || "";
    if (st) {
      st.textContent = running
        ? "Discovering…"
        : job.status === "done"
          ? job.message || "Discover done."
          : job.status === "error"
            ? job.error || "Discover error."
            : "Idle.";
    }
  }

  function renderScrape(job, live) {
    const box = $("swaScrapeProgress");
    const bar = $("swaScrapeBar");
    const msg = $("swaScrapeMsg");
    const st = $("swaScrapeStatus");
    const running = job.status === "running";
    if (box) box.hidden = !job.status || job.status === "idle";
    if (bar) bar.style.width = `${Math.max(0, Math.min(100, Number(job.progress) || 0))}%`;
    const lines = [(job.message || "").split("\n")[0] || ""];
    (live || []).slice(0, 12).forEach((row) => {
      lines.push(
        `#${row.id} ${row.phase || "?"} · ${(row.title || "").slice(0, 48)} · ${(row.detail || "").slice(0, 60)}`
      );
    });
    if (msg) msg.textContent = lines.filter(Boolean).join("\n");
    if (st) {
      st.textContent = running
        ? `Scraping · ${job.completed || 0}/${job.total || "?"} · ${job.hits || 0} hits`
        : job.status === "done"
          ? job.message || "Scrape done."
          : job.status === "error"
            ? job.error || "Scrape error."
            : "Idle.";
    }
  }

  async function loadQueue() {
    const body = $("swaQueueBody");
    const meta = $("swaQueueMeta");
    if (!body) return;
    let data;
    try {
      data = await apiGet(`/api/swa/queue?offset=${queueOffset}&limit=40`);
    } catch {
      return;
    }
    const items = data.items || [];
    if (!items.length) {
      body.innerHTML = `<tr><td colspan="4">No SWA queue rows.</td></tr>`;
    } else {
      body.innerHTML = items
        .map(
          (r) => `<tr>
            <td>${escapeHtml(r.id)}</td>
            <td>${escapeHtml(r.status)}</td>
            <td>${
              r.hub_url || r.url
                ? `<a href="${escapeAttr(r.hub_url || r.url)}" target="_blank" rel="noopener">${escapeHtml((r.title || "").slice(0, 80))}</a>`
                : escapeHtml((r.title || "").slice(0, 80))
            }</td>
            <td>${escapeHtml(r.source || "")}</td>
          </tr>`
        )
        .join("");
    }
    if (meta) {
      meta.textContent = `Showing ${items.length} · total ${data.total ?? data.n_queue ?? "—"}`;
    }
  }

  $("swaFullMode")?.addEventListener("change", (e) => {
    const wrap = $("swaMaxPagesWrap");
    if (wrap) wrap.hidden = !e.target.checked;
  });

  $("swaDiscoverBtn")?.addEventListener("click", async () => {
    const raw = ($("swaKeywords")?.value || "").trim();
    const keywords = raw
      ? raw.split(/[,;\n]+/).map((s) => s.trim()).filter(Boolean)
      : null;
    const max_per_query = Number($("swaMaxPer")?.value || 40);
    const full = $("swaFullMode")?.checked || false;
    const res = await apiPost("/api/swa/discover", {
      keywords,
      max_per_query,
      mode: full ? "full" : "autocomplete",
      max_pages: Number($("swaMaxPages")?.value || 5),
    });
    if (!res.ok) {
      alert(res.error || "Discover busy");
      return;
    }
    poller.kick();
  });

  $("swaScrapeBtn")?.addEventListener("click", async () => {
    const res = await apiPost("/api/swa/scrape", {
      max_images: $("swaScrapeMax")?.value || "all",
      workers: Number($("swaWorkers")?.value || 4),
    });
    if (!res.ok) {
      alert(res.error || "Scrape busy");
      return;
    }
    poller.kick();
  });

  $("swaStopBtn")?.addEventListener("click", async () => {
    await apiPost("/api/swa/scrape/stop", {});
    poller.kick();
  });

  $("swaClearBtn")?.addEventListener("click", async () => {
    if (!confirm("Clear all SWA queue rows?")) return;
    await apiPost("/api/swa/queue/clear", {});
    poller.kick();
  });

  poller.start();
})();
