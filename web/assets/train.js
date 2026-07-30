/* Train hub: label clips (Pathé / YouTube reference) plus the Frames (probe) tab. */
let query = "";
let mode = ""; // "" | "youtube"
let clips = [];
let stats = { n_total: 0, n_pending: 0, n_yes: 0, n_no: 0 };
let activeId = null;
let status = "pending";
let search = "";
let seedPoll = null;
let activeTab = "clips";

function isYoutubeUrl(s) {
  return /youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\//i.test(
    String(s || "")
  );
}

function isPatheAssetUrl(s) {
  return /britishpathe\.com\/asset\/\d+/i.test(String(s || ""));
}

function normalizePatheAssetUrl(s) {
  const m = String(s || "").match(/britishpathe\.com\/asset\/(\d+)/i);
  return m ? `https://www.britishpathe.com/asset/${m[1]}/` : String(s || "").trim();
}

function decisionLabel(d) {
  const x = String(d || "").trim();
  if (x === "yes" || x === "accept") return "Orthodox Jew";
  if (x === "no" || x === "reject") return "Not Orthodox";
  return "Untagged";
}

function decisionClass(d) {
  const x = String(d || "").trim();
  if (x === "yes" || x === "accept") return "accept";
  if (x === "no" || x === "reject") return "reject";
  return "pending";
}

function normalizeClip(c) {
  const d = { ...c };
  const dec = (d.decision || "").trim();
  if (dec === "accept") d.decision = "yes";
  else if (dec === "reject") d.decision = "no";
  if (!d.thumb_url) {
    d.thumb_url =
      d.contact_url ||
      d.image_url ||
      d.still_url ||
      (d.id != null ? `/media/sheet/cand_${d.id}.jpg` : "");
  }
  if (!d.url) d.url = d.source_url || "";
  if (!d.asset_id) d.asset_id = d.video_id || d.id;
  if (!d.title) d.title = d.video_id || "Clip";
  return d;
}

function readQuery() {
  const el = $("trainQuery");
  query = (el?.value || "").trim();
  if (isYoutubeUrl(query)) {
    mode = "youtube";
  } else if (isPatheAssetUrl(query)) {
    query = normalizePatheAssetUrl(query);
    if (el && el.value.trim() !== query) el.value = query;
    mode = "asset";
  } else {
    mode = query ? "pathe" : "";
  }
  return query;
}

function activeClip() {
  return clips.find((c) => Number(c.id) === Number(activeId)) || null;
}

function renderStats() {
  const el = $("trainStats");
  if (!el) return;
  const label =
    mode === "youtube"
      ? "YouTube reference"
      : mode === "asset"
        ? `Asset ${query.match(/\/asset\/(\d+)/)?.[1] || query}`
        : query
          ? `Search “${query}”`
          : "—";
  el.textContent =
    `${label} · ${stats.n_total || 0} clips · ${stats.n_pending || 0} to tag · ` +
    `${stats.n_yes || 0} Orthodox · ${stats.n_no || 0} not`;
}

function renderList() {
  const list = $("list");
  if (!list) return;
  if (!query && mode !== "youtube") {
    list.innerHTML = `<div class="card" style="cursor:default">
      <div class="title">No source yet</div>
      <div class="cue">Paste a Pathé keyword, Pathé asset URL, or a YouTube URL, then Load.</div>
    </div>`;
    return;
  }
  if (!clips.length) {
    list.innerHTML = `<div class="card" style="cursor:default">
      <div class="title">${mode === "youtube" ? "Scanning…" : "No clips yet"}</div>
      <div class="cue">${
        mode === "youtube"
          ? "Local scan running — frame hits appear here when segments are saved."
          : mode === "asset"
            ? `Press “Load” to resolve asset ${escapeHtml(query.match(/\/asset\/(\d+)/)?.[1] || query)}.`
            : `Press “Load” for “${escapeHtml(query)}”.`
      }</div>
    </div>`;
    return;
  }
  list.innerHTML = clips
    .map((c) => {
      const d = (c.decision || "").trim();
      const active = Number(c.id) === Number(activeId) ? " active" : "";
      const thumb = (c.thumb_url || "").trim();
      const thumbHtml = thumb
        ? `<img class="train-thumb" src="${escapeAttr(thumb)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
        : `<div class="train-thumb train-thumb-empty"></div>`;
      const cue =
        mode === "youtube"
          ? `${Number(c.rank_score || 0).toFixed(3)} · ${escapeHtml(c.best_cue || "hit")}`
          : escapeHtml(c.year || "British Pathé");
      return `<button class="card train-card${active}" type="button" data-id="${c.id}">
        ${thumbHtml}
        <div class="train-card-body">
          <div class="meta">
            <span>#${escapeHtml(c.asset_id || c.id)}</span>
            <span class="badge ${decisionClass(d)}">${escapeHtml(decisionLabel(d))}</span>
          </div>
          <div class="title">${escapeHtml(c.title || "Untitled")}</div>
          <div class="cue">${cue}</div>
        </div>
      </button>`;
    })
    .join("");
  list.querySelectorAll("[data-id]").forEach((btn) => {
    btn.addEventListener("click", () => selectClip(Number(btn.dataset.id)));
  });
}

function renderDetail() {
  const detail = $("detail");
  const c = activeClip();
  if (!detail) return;
  if (!c) {
    detail.innerHTML = `<div class="sheet placeholder">Select a clip</div>`;
    return;
  }
  const d = (c.decision || "").trim();
  const thumb = (c.thumb_url || "").trim();
  const url = (c.url || "").trim();
  const media = thumb
    ? `<a class="watch-link" href="${escapeAttr(url)}" target="_blank" rel="noopener">
         <img class="sheet" src="${escapeAttr(thumb)}" alt=""
           referrerpolicy="no-referrer"
           onerror="this.classList.add('broken'); this.alt='Preview unavailable';" />
       </a>`
    : `<div class="sheet placeholder">Still loading…</div>`;

  detail.innerHTML = `
    <div class="hit-stage">
      ${media}
      <div class="hit-overlay">
        <span class="badge ${decisionClass(d)}">${escapeHtml(decisionLabel(d))}</span>
      </div>
    </div>
    <a class="watch-link" href="${escapeAttr(url)}" target="_blank" rel="noopener">
      <span class="watch-icon">▶</span>
      <span>
        <strong>${mode === "youtube" ? "Open on YouTube" : "Open on British Pathé"}</strong>
        <small>Watch, then confirm the tag</small>
      </span>
    </a>
    <header class="hit-head">
      <h2>${escapeHtml(c.title || "Untitled")}</h2>
      <p class="hit-cue">${escapeHtml(
        mode === "youtube"
          ? `${c.best_cue || "scan hit"} · score ${Number(c.rank_score || 0).toFixed(3)}`
          : `Asset ${c.asset_id || ""}${c.year ? " · " + c.year : ""}`
      )}</p>
    </header>
    <div class="actions hit-decide">
      <button class="btn ok" data-act="yes">Orthodox Jew</button>
      <button class="btn danger" data-act="no">Not</button>
      <button class="btn ghost small" data-act="clear">Undo</button>
    </div>
    <textarea class="notes" id="notes" placeholder="Optional note…">${escapeHtml(c.notes || "")}</textarea>
    <p class="hit-hint">Keys: A = Orthodox · R = Not · ← → next clip</p>
  `;

  detail.querySelectorAll("[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => labelClip(btn.dataset.act));
  });
}

async function labelClip(decision) {
  const c = activeClip();
  if (!c) return;
  const notes = $("notes")?.value || "";
  const data = await apiPost("/api/train/label", {
    id: c.id,
    decision,
    notes,
    mode: mode === "youtube" ? "youtube" : "",
    candidate: mode === "youtube",
  });
  if (!data.ok) {
    setStatus(data.error || "Label failed");
    return;
  }
  const idx = clips.findIndex((x) => Number(x.id) === Number(c.id));
  if (idx >= 0 && data.clip) clips[idx] = normalizeClip(data.clip);
  if (decision === "yes" || decision === "no") {
    const next =
      clips.find((x, i) => i > idx && !(x.decision || "").trim()) ||
      clips[Math.min(idx + 1, clips.length - 1)];
    await fetchClips();
    if (next) selectClip(Number(next.id));
    else renderDetail();
  } else {
    await fetchClips();
    selectClip(Number(c.id));
  }
}

function selectClip(id) {
  activeId = id;
  renderList();
  renderDetail();
  const card = document.querySelector(`.card[data-id="${id}"]`);
  if (card) card.scrollIntoView({ block: "nearest" });
}

function setStatus(msg) {
  const el = $("trainStatus");
  if (el) el.textContent = msg || "";
}

function setStatusFromSeed(seed) {
  const el = $("trainStatus");
  if (!el) return;
  const msg = (seed && seed.message) || "";
  if (!seed || seed.status !== "running") {
    el.textContent = msg;
    return;
  }
  const pct =
    seed.progress != null && !Number.isNaN(Number(seed.progress))
      ? Math.round(Number(seed.progress))
      : null;
  const hits =
    seed.hits != null && !Number.isNaN(Number(seed.hits))
      ? Number(seed.hits)
      : null;
  const bits = [];
  if (pct != null) bits.push(`${pct}%`);
  if (msg) bits.push(msg);
  if (hits > 0) bits.push(`${hits} frame hits`);
  el.textContent = bits.join(" · ") || "Local scan running…";
}

async function fetchSummary() {
  readQuery();
  const data = await apiGet("/api/train/summary");
  if (data.youtube_ref && !query) {
    query = data.youtube_ref.url || "";
    mode = "youtube";
    const el = $("trainQuery");
    if (el && !el.value) el.value = query;
  }
  if (mode === "youtube" && data.youtube_stats) stats = data.youtube_stats;
  else stats = data.stats || stats;
  renderStats();
  const seed = data.seed || {};
  if (seed.status === "running") {
    setStatusFromSeed(seed);
    if (!seedPoll) seedPoll = setInterval(pollSeed, 2000);
  }
  return data;
}

async function fetchClips() {
  readQuery();
  if (mode === "youtube") {
    const params = new URLSearchParams({ status, limit: "500" });
    const data = await apiGet("/api/train/youtube?" + params);
    clips = (data.clips || []).map(normalizeClip);
    if (search) {
      const q = search.toLowerCase();
      clips = clips.filter(
        (c) =>
          String(c.title || "").toLowerCase().includes(q) ||
          String(c.best_cue || "").toLowerCase().includes(q)
      );
    }
    stats = data.stats || stats;
    if (data.ref?.url) {
      query = data.ref.url;
      mode = "youtube";
      const el = $("trainQuery");
      if (el) el.value = query;
    }
  } else if (!query) {
    clips = [];
    stats = { n_total: 0, n_pending: 0, n_yes: 0, n_no: 0 };
  } else {
    const params = new URLSearchParams({
      query,
      status,
      limit: "500",
    });
    if (search) params.set("q", search);
    const data = await apiGet("/api/train/clips?" + params);
    clips = (data.clips || []).map(normalizeClip);
    stats = data.stats || stats;
  }
  renderStats();
  renderList();
  if (activeId && clips.some((c) => Number(c.id) === Number(activeId))) {
    renderDetail();
  } else if (clips.length) {
    selectClip(Number(clips[0].id));
  } else {
    activeId = null;
    renderDetail();
  }
}

async function pollSeed() {
  const data = await fetchSummary();
  const seed = data.seed || {};
  await fetchClips();
  if (mode === "youtube") {
    if (seed.status === "running" || (stats.n_total || 0) === 0) {
      setStatusFromSeed(seed);
      return;
    }
  }
  if (seed.status === "running") {
    setStatusFromSeed(seed);
    return;
  }
  if (seedPoll) {
    clearInterval(seedPoll);
    seedPoll = null;
  }
  setStatus(seed.message || (mode === "youtube" ? "YouTube reference ready" : ""));
  if (mode !== "youtube") await ensureThumbs();
}

async function loadSearch() {
  if (!readQuery()) {
    setStatus("Enter a Pathé search query or YouTube URL first");
    return;
  }
  const btn = $("loadBtn");
  if (btn) btn.disabled = true;
  try {
    if (mode === "youtube") {
      setStatus("Queuing YouTube video for Orthodox training scan…");
      const data = await apiPost("/api/train/youtube", {
        url: query,
        title: "Orthodox look training reference",
      });
      if (!data.ok) {
        setStatus(data.error || "Could not start YouTube training scan");
        return;
      }
      const scan = data.scan || data.scrape || {};
      const scrapeMsg = scan.deferred
        ? `GPU ${scan.backend || "runpod"} scan started`
        : scan.ok
          ? `GPU scrape started (${scan.backend || "runpod"})`
          : scan.error || "queued";
      setStatus(`${scrapeMsg}. Hits auto-tag as Orthodox for few-shot.`);
      if (!seedPoll) seedPoll = setInterval(pollSeed, 2000);
      await pollSeed();
      return;
    }

    setStatus(
      mode === "asset"
        ? `Loading Pathé asset…`
        : `Starting Pathé discover for “${query}”…`
    );
    const data = await apiPost("/api/train/seed", {
      query,
      max_items: mode === "asset" ? 1 : 500,
      resume: false,
    });
    if (!data.ok) {
      setStatus(data.error || "Could not start load");
      return;
    }
    if (data.query) {
      query = data.query;
      const el = $("trainQuery");
      if (el) el.value = query;
      mode = isPatheAssetUrl(query) ? "asset" : mode;
    }
    if (!seedPoll) seedPoll = setInterval(pollSeed, 1500);
    await pollSeed();
  } finally {
    if (btn) btn.disabled = false;
  }
}

function syncLoadButtonLabel() {
  const btn = $("loadBtn");
  if (!btn) return;
  readQuery();
  btn.textContent =
    mode === "youtube"
      ? "Scan YouTube on GPU"
      : mode === "asset"
        ? "Load Pathé asset"
        : "Load Pathé search";
}

async function scoreThese() {
  if (mode === "youtube") {
    // Re-run GPU train scan (does not mean Pathé "Score these").
    await loadSearch();
    return;
  }
  if (!readQuery()) {
    setStatus("Enter a Pathé search query first");
    return;
  }
  const btn = $("scanBtn");
  if (btn) btn.disabled = true;
  setStatus("Queuing clips for GPU score…");
  try {
    const data = await apiPost("/api/train/scan", { query, only: "all" });
    if (!data.ok) {
      setStatus(data.error || "Scan failed to start");
      return;
    }
    const n = data.n_clips || 0;
    const added = data.queued?.n_added ?? "—";
    setStatus(
      `Queued ${n} clips (${added} new) — scrape started. Watch console / Pathé page.`
    );
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* Single CLIP-train action shared by both tabs. */
async function startClipTrain(payload, btn, startMsg) {
  if (btn) btn.disabled = true;
  setStatus(startMsg);
  try {
    const data = await apiPost("/api/train/clip", payload);
    if (!data.ok) {
      setStatus(data.error || "CLIP train failed to start");
      if (btn) btn.disabled = false;
      return;
    }
    setStatus(data.job?.message || "CLIP train running…");
    if (seedPoll) clearInterval(seedPoll);
    seedPoll = setInterval(async () => {
      try {
        const sdata = await apiGet("/api/train/summary");
        const job = sdata.clip_ft || {};
        const m = sdata.clip_metrics || {};
        if (job.message) setStatus(job.message);
        if (job.status === "done") {
          clearInterval(seedPoll);
          seedPoll = null;
          const auc = m.val_auc != null ? ` · auc=${Number(m.val_auc).toFixed(2)}` : "";
          const acc = m.val_acc != null ? ` · acc=${Number(m.val_acc).toFixed(2)}` : "";
          setStatus((job.message || "CLIP probe ready") + acc + auc);
          if (btn) btn.disabled = false;
        } else if (job.status === "error") {
          clearInterval(seedPoll);
          seedPoll = null;
          setStatus(job.message || job.error || "CLIP train failed");
          if (btn) btn.disabled = false;
        }
      } catch (_) {
        /* ignore poll blips */
      }
    }, 2000);
  } catch (e) {
    setStatus("CLIP train request failed");
    if (btn) btn.disabled = false;
  }
}

async function clearSet() {
  if (!confirm("Clear the whole training set? Labels will be deleted.")) return;
  const data = await apiPost("/api/train/clear", {});
  clips = [];
  activeId = null;
  mode = "";
  query = "";
  const el = $("trainQuery");
  if (el) el.value = "";
  stats = { n_total: 0, n_pending: 0, n_yes: 0, n_no: 0 };
  setStatus(data.ok ? `Cleared ${data.deleted || 0} clip(s)` : data.error || "Clear failed");
  renderStats();
  renderList();
  renderDetail();
}

async function ensureThumbs() {
  if (!query || mode === "youtube" || mode === "asset") return;
  const missing = clips.filter((c) => !(c.thumb_url || "").trim()).length;
  if (!missing) return;
  setStatus(`Fetching stills for ${missing} clip(s)…`);
  try {
    const data = await apiPost("/api/train/thumbs", { query, max_pages: 12 });
    if (data.ok) {
      setStatus(
        data.updated
          ? `Loaded ${data.updated} still(s) from Pathé`
          : "No new stills found — open Pathé for each clip"
      );
      await fetchClips();
    } else {
      setStatus(data.error || "Could not fetch stills");
    }
  } catch (e) {
    setStatus("Could not fetch stills");
  }
}

/* —— Frames tab (probe frames include/exclude) —— */

let probeLabel = "all";
let probeStatusFilter = "all";
let probeOffset = 0;
const probeLimit = 120;
let probeItems = [];
let probeBusy = false;

async function loadFrames() {
  const statusEl = $("probeStatus");
  const statsEl = $("probeStats");
  const grid = $("probeGrid");
  const pager = $("probePager");
  if (!statusEl || !grid) return;
  statusEl.textContent = "Loading frames…";
  const qs = new URLSearchParams({
    label: probeLabel,
    status: probeStatusFilter,
    limit: String(probeLimit),
    offset: String(probeOffset),
  });
  try {
    const j = await apiGet(`/api/clip_ft/frames?${qs}`);
    if (!j.ok) {
      statusEl.textContent = `Load failed: ${j.error || j.status}`;
      return;
    }
    probeItems = j.items || [];
    const c = j.counts || {};
    if (statsEl) {
      statsEl.textContent =
        `Train as good: ${c.keep_included ?? 0} Keep · ` +
        `Train as wrong: ${(c.pass_included ?? 0) + (c.excluded ?? 0)} ` +
        `(${c.pass_included ?? 0} Pass included + ${c.excluded ?? 0} excluded) · ` +
        `on disk Keep ${c.keep ?? 0} / Pass ${c.pass ?? 0}`;
    }
    grid.innerHTML = probeItems
      .map((it) => {
        const on = it.included;
        const meta = [
          it.label,
          it.cand_id != null ? `#${it.cand_id}` : null,
          it.time_sec != null ? fmtTimeFrac(it.time_sec) : it.name.includes("_still") ? "still" : null,
        ]
          .filter(Boolean)
          .join(" · ");
        return `<figure class="frame-card frame-cover ${on ? "is-in" : "is-out"}" data-path="${escapeAttr(
          it.path
        )}" tabindex="0" role="button" aria-pressed="${on ? "true" : "false"}">
          <img src="${escapeAttr(it.url)}" alt="${escapeAttr(it.path)}" loading="lazy" />
          <figcaption>${escapeHtml(meta)}</figcaption>
          <span class="frame-flag">${on ? "Included · good if Keep" : "Excluded · trains as wrong"}</span>
        </figure>`;
      })
      .join("");
    const total = Number(j.total) || 0;
    const pg = pagerText(probeOffset, probeLimit, total);
    statusEl.textContent = total
      ? `Showing ${pg.start}–${pg.end} of ${total}`
      : "No frames in dataset — run deep CLIP export first.";
    if (pager) pager.hidden = total <= probeLimit;
    const pageLabel = $("probePageLabel");
    if (pageLabel) pageLabel.textContent = `${pg.start}–${pg.end} / ${total}`;
    const prev = $("probePrev");
    const next = $("probeNext");
    if (prev) prev.disabled = pg.prevDisabled;
    if (next) next.disabled = pg.nextDisabled;
  } catch (err) {
    statusEl.textContent = `Load failed: ${err.message || err}`;
  }
}

async function setExcluded(paths, excluded) {
  if (!paths.length || probeBusy) return;
  probeBusy = true;
  const statusEl = $("probeStatus");
  try {
    const j = await apiPost("/api/clip_ft/exclude", { paths, excluded });
    if (!j.ok) {
      statusEl.textContent = `Update failed: ${j.error || j.status}`;
      return;
    }
    await loadFrames();
  } catch (err) {
    statusEl.textContent = `Update failed: ${err.message || err}`;
  } finally {
    probeBusy = false;
  }
}

function bindFramesTab() {
  const grid = $("probeGrid");
  if (!grid) return;

  grid.addEventListener("click", (e) => {
    const card = e.target.closest(".frame-card");
    if (!card) return;
    const path = card.dataset.path;
    const item = probeItems.find((x) => x.path === path);
    if (!item) return;
    setExcluded([path], item.included); // toggle → exclude if currently included
  });

  grid.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const card = e.target.closest(".frame-card");
    if (!card) return;
    e.preventDefault();
    card.click();
  });

  $("labelChips").addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    probeLabel = btn.dataset.label || "all";
    probeOffset = 0;
    setChipGroup("labelChips", "label", probeLabel);
    loadFrames();
  });

  $("probeStatusChips").addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    probeStatusFilter = btn.dataset.status || "all";
    probeOffset = 0;
    setChipGroup("probeStatusChips", "status", probeStatusFilter);
    loadFrames();
  });

  $("probeIncludeAll").addEventListener("click", () => {
    setExcluded(
      probeItems.map((i) => i.path),
      false
    );
  });

  $("probeExcludeAll").addEventListener("click", () => {
    setExcluded(
      probeItems.map((i) => i.path),
      true
    );
  });

  $("probePrev").addEventListener("click", () => {
    probeOffset = Math.max(0, probeOffset - probeLimit);
    loadFrames();
  });

  $("probeNext").addEventListener("click", () => {
    probeOffset += probeLimit;
    loadFrames();
  });

  $("probeTrain").addEventListener("click", (e) => {
    startClipTrain(
      { export: false, deep: false },
      e.currentTarget,
      "Starting CLIP train from included frames…"
    );
  });
}

/* —— UI wiring —— */

function bindUi() {
  $("statusChips")?.querySelectorAll("[data-status]").forEach((chip) => {
    chip.addEventListener("click", async () => {
      document
        .querySelectorAll("#statusChips .chip")
        .forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      status = chip.dataset.status ?? "";
      activeId = null;
      await fetchClips();
    });
  });

  $("search")?.addEventListener(
    "input",
    debounce(async (e) => {
      search = e.target.value || "";
      await fetchClips();
    }, 220)
  );

  $("trainQuery")?.addEventListener("input", () => {
    syncLoadButtonLabel();
  });
  $("trainQuery")?.addEventListener("change", () => {
    readQuery();
    syncLoadButtonLabel();
    fetchClips();
  });

  $("loadBtn")?.addEventListener("click", loadSearch);
  $("scanBtn")?.addEventListener("click", scoreThese);
  $("clipBtn")?.addEventListener("click", (e) =>
    startClipTrain({}, e.currentTarget, "Training CLIP probe from Keep/Pass stills…")
  );
  $("clearBtn")?.addEventListener("click", clearSet);

  window.addEventListener("keydown", (e) => {
    if (activeTab !== "clips") return;
    if (e.target && ["INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
    const idx = clips.findIndex((c) => Number(c.id) === Number(activeId));
    if (e.key === "a" || e.key === "A") {
      e.preventDefault();
      labelClip("yes");
    } else if (e.key === "r" || e.key === "R" || e.key === "x" || e.key === "X") {
      e.preventDefault();
      labelClip("no");
    } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      if (idx >= 0 && idx < clips.length - 1) selectClip(Number(clips[idx + 1].id));
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      if (idx > 0) selectClip(Number(clips[idx - 1].id));
    }
  });
}

(async function init() {
  renderNav("train");
  bindUi();
  bindFramesTab();
  initTabs("clips", (tab) => {
    activeTab = tab;
    if (tab === "frames") loadFrames();
  });
  await fetchSummary();
  syncLoadButtonLabel();
  await fetchClips();
  if (!query) {
    setStatus("Paste a YouTube URL or Pathé search, then Load.");
  }
})();
