/* Thumbnail gallery — infinite scroll through all filtered stills. */
const Gallery = (() => {
  let rows = [];
  let filter = "all";
  let query = "";
  let sortKey = "score";
  let sortDir = "desc";
  let selectedKey = "";
  let busy = false;
  let loaded = false;
  let visibleCount = 48;
  let pageSize = 48;
  let sentinelObs = null;

  function prettyTitle(videoId) {
    return String(videoId || "Untitled")
      .replace(/[_]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/\b\w/g, (ch) => ch.toUpperCase());
  }

  function fmtTime(sec) {
    const n = Math.max(0, Math.floor(Number(sec) || 0));
    const m = Math.floor(n / 60);
    const s = n % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function aiTag(notes) {
    const lines = String(notes || "")
      .split(/\n+/)
      .map((ln) => ln.trim())
      .filter(Boolean);
    if (lines.some((ln) => /^(openai|vlm):keep\b/i.test(ln))) return "keep";
    if (lines.some((ln) => /^(openai|vlm):drop\b/i.test(ln))) return "drop";
    if (lines.some((ln) => /^(openai|vlm):uncertain\b/i.test(ln))) return "uncertain";
    return "none";
  }

  function apiFilterParam(f) {
    if (f === "openai_keep") return { status: "openai_keep" };
    if (f === "openai_drop") return { status: "openai_drop" };
    if (f === "openai_none") return { status: "openai_none" };
    if (f === "pending") return { status: "pending" };
    if (f === "accept") return { status: "accept" };
    if (f === "reject") return { status: "reject" };
    return { status: "all" };
  }

  function filteredRows() {
    const q = query.toLowerCase();
    let list = rows.slice();
    if (q) {
      list = list.filter(
        (r) =>
          String(r.video_id || "").toLowerCase().includes(q) ||
          String(r.best_cue || "").toLowerCase().includes(q)
      );
    }
    const mul = sortDir === "asc" ? 1 : -1;
    list.sort((a, b) => {
      if (sortKey === "scored") {
        return mul * ((Number(a.created_at) || 0) - (Number(b.created_at) || 0));
      }
      return mul * ((Number(a.rank_score) || 0) - (Number(b.rank_score) || 0));
    });
    return list;
  }

  function stillUrl(c) {
    const cloud = (c.image_url || "").includes("litter.catbox.moe") ? "" : c.image_url || "";
    return c.contact_url || cloud || "";
  }

  function ensureVisible(idx) {
    if (idx + 1 > visibleCount) {
      visibleCount = Math.min(
        filteredRows().length,
        Math.ceil((idx + 1) / pageSize) * pageSize
      );
    }
  }

  function revealMore() {
    const total = filteredRows().length;
    if (visibleCount >= total) return false;
    visibleCount = Math.min(total, visibleCount + pageSize);
    render({ keepScroll: true });
    return true;
  }

  function cardHtml(c, index) {
    const key = String(c.key);
    const decision = (c.decision || "").trim();
    const ai = aiTag(c.notes);
    const img = stillUrl(c);
    const title = prettyTitle(c.video_id);
    const sel = key === String(selectedKey) ? " is-selected" : "";
    const decCls =
      decision === "accept" ? " is-accept" : decision === "reject" ? " is-reject" : "";
    const aiBadge =
      ai === "keep"
        ? `<span class="badge ai-keep">AI pass</span>`
        : ai === "drop"
          ? `<span class="badge ai-drop">AI fail</span>`
          : ai === "uncertain"
            ? `<span class="badge ai-none">AI ?</span>`
            : `<span class="badge ai-none">No AI</span>`;
    const humBadge =
      decision === "accept"
        ? `<span class="badge accept">Kept</span>`
        : decision === "reject"
          ? `<span class="badge reject">Passed</span>`
          : `<span class="badge pending">Check</span>`;
    const media = img
      ? `<img class="gallery-thumb" src="${escapeAttr(img)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
      : `<div class="gallery-thumb-empty">No still</div>`;
    return `<article class="gallery-card${sel}${decCls}" data-key="${escapeAttr(key)}" tabindex="-1">
      <span class="gallery-num">${index}</span>
      <div class="gallery-badges">${aiBadge}${humBadge}</div>
      ${media}
      <div class="gallery-meta">
        <strong title="${escapeAttr(title)}">${escapeHtml(title)}</strong>
        ${fmtTime(c.start_sec)} · ${Number(c.rank_score || 0).toFixed(3)}
      </div>
      <div class="gallery-actions">
        <button type="button" class="btn ok" data-act="accept" data-key="${escapeAttr(key)}">Keep</button>
        <button type="button" class="btn danger" data-act="reject" data-key="${escapeAttr(key)}">Pass</button>
      </div>
    </article>`;
  }

  function renderPager(shown, total) {
    const label = $("galleryPageLabel");
    const prev = $("galleryPrev");
    const next = $("galleryNext");
    if (label) {
      label.textContent =
        shown >= total
          ? `All ${total}`
          : `${shown} of ${total} · scroll for more`;
    }
    if (prev) {
      prev.textContent = "↑ Top";
      prev.disabled = false;
    }
    if (next) {
      next.textContent = "More ↓";
      next.disabled = shown >= total;
    }
  }

  function bindSentinel() {
    if (sentinelObs) {
      sentinelObs.disconnect();
      sentinelObs = null;
    }
    const el = $("gallerySentinel");
    if (!el || typeof IntersectionObserver === "undefined") return;
    sentinelObs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) revealMore();
      },
      { root: null, rootMargin: "600px 0px", threshold: 0 }
    );
    sentinelObs.observe(el);
  }

  function render(opts = {}) {
    const grid = $("galleryGrid");
    const summary = $("gallerySummary");
    if (!grid || !summary) return;
    const list = filteredRows();
    visibleCount = Math.min(Math.max(pageSize, visibleCount), list.length || pageSize);
    const slice = list.slice(0, visibleCount);
    const nKeep = list.filter((r) => r.decision === "accept").length;
    const nPass = list.filter((r) => r.decision === "reject").length;
    const nPend = list.filter((r) => !(r.decision || "").trim()).length;
    const nAiKeep = list.filter((r) => aiTag(r.notes) === "keep").length;
    const nAiDrop = list.filter((r) => aiTag(r.notes) === "drop").length;
    const nAiUnc = list.filter((r) => aiTag(r.notes) === "uncertain").length;
    const nAiNone = list.filter((r) => aiTag(r.notes) === "none").length;
    summary.textContent =
      `Showing ${slice.length} of ${list.length}` +
      ` · AI pass ${nAiKeep} · AI fail ${nAiDrop}` +
      (nAiUnc ? ` · AI ? ${nAiUnc}` : "") +
      ` · not sent ${nAiNone}` +
      ` · kept ${nKeep} · passed ${nPass} · to check ${nPend}`;
    renderPager(slice.length, list.length);

    if (!list.length) {
      grid.innerHTML = `<div class="sheet placeholder" style="grid-column:1/-1">No stills for this filter.</div>`;
      return;
    }

    if (!selectedKey || !list.some((r) => String(r.key) === String(selectedKey))) {
      selectedKey = String(list[0].key);
    } else if (!slice.some((r) => String(r.key) === String(selectedKey))) {
      // Selection is below the fold — reveal enough to include it.
      const idx = list.findIndex((r) => String(r.key) === String(selectedKey));
      if (idx >= 0) ensureVisible(idx);
    }

    const shown = list.slice(0, visibleCount);
    const more = shown.length < list.length;
    grid.innerHTML =
      shown.map((c, i) => cardHtml(c, i + 1)).join("") +
      (more
        ? `<div class="gallery-sentinel" id="gallerySentinel" style="grid-column:1/-1">Loading more…</div>`
        : `<div class="gallery-end" style="grid-column:1/-1">End of gallery · ${list.length} stills</div>`);

    bindSentinel();
    if (!opts.keepScroll) scrollSelectedIntoView();
  }

  function scrollSelectedIntoView() {
    const grid = $("galleryGrid");
    if (!grid) return;
    const card = grid.querySelector(`.gallery-card[data-key="${String(selectedKey)}"]`);
    if (card) card.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  async function fetchRows() {
    const summary = $("gallerySummary");
    if (summary) summary.textContent = "Loading…";
    visibleCount = pageSize;
    const params = apiFilterParam(filter);
    const qs = new URLSearchParams({
      limit: "20000",
      status: params.status,
    });
    if (query) qs.set("q", query);
    const data = await apiGet(`/api/candidates?${qs.toString()}`);
    rows = data.candidates || [];
    loaded = true;
    render();
  }

  async function mark(key, decision) {
    if (busy || !key) return;
    busy = true;
    try {
      await apiPost("/api/review", { key: String(key), decision });
      const row = rows.find((r) => String(r.key) === String(key));
      if (row) row.decision = decision === "clear" ? "" : decision;
      if (decision === "accept" || decision === "reject") {
        const list = filteredRows();
        const idx = list.findIndex((r) => String(r.key) === String(key));
        if (idx >= 0 && idx < list.length - 1) {
          selectedKey = String(list[idx + 1].key);
          ensureVisible(idx + 1);
        }
      } else {
        selectedKey = String(key);
      }
      render();
    } catch (e) {
      if ($("gallerySummary")) {
        $("gallerySummary").textContent = `Could not save: ${e.message || e}`;
      }
    } finally {
      busy = false;
    }
  }

  function selectKey(key) {
    selectedKey = String(key || "");
    const list = filteredRows();
    const idx = list.findIndex((r) => String(r.key) === String(selectedKey));
    if (idx >= 0) ensureVisible(idx);
    render();
  }

  function step(delta) {
    const list = filteredRows();
    if (!list.length) return;
    let idx = list.findIndex((r) => String(r.key) === String(selectedKey));
    if (idx < 0) idx = 0;
    else idx = Math.max(0, Math.min(list.length - 1, idx + delta));
    // If moving past currently rendered tiles, grow the window first.
    if (idx >= visibleCount) {
      visibleCount = Math.min(list.length, idx + 1 + pageSize);
    }
    selectedKey = String(list[idx].key);
    render();
  }

  function onGridClick(e) {
    const actBtn = e.target.closest("[data-act]");
    if (actBtn) {
      e.preventDefault();
      e.stopPropagation();
      mark(actBtn.dataset.key, actBtn.dataset.act);
      return;
    }
    const card = e.target.closest(".gallery-card");
    if (card) selectKey(card.dataset.key);
  }

  function onKey(e) {
    const pane = document.querySelector('.tab-pane[data-tab="gallery"]');
    if (!pane || pane.hidden) return;
    const tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (e.key === "ArrowRight" || e.key === "ArrowDown" || e.key === "j" || e.key === "J") {
      e.preventDefault();
      step(1);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp" || e.key === "k" || e.key === "K") {
      e.preventDefault();
      step(-1);
    } else if (e.key === "]" || e.key === "PageDown") {
      e.preventDefault();
      revealMore();
      window.scrollBy({ top: Math.max(240, window.innerHeight * 0.7), behavior: "smooth" });
    } else if (e.key === "[" || e.key === "PageUp") {
      e.preventDefault();
      window.scrollBy({ top: -Math.max(240, window.innerHeight * 0.7), behavior: "smooth" });
    } else if (e.key === "a" || e.key === "A") {
      e.preventDefault();
      mark(selectedKey, "accept");
    } else if (e.key === "r" || e.key === "R" || e.key === "x" || e.key === "X") {
      e.preventDefault();
      mark(selectedKey, "reject");
    } else if (e.key === "u" || e.key === "U") {
      e.preventDefault();
      mark(selectedKey, "clear");
    }
  }

  function wire() {
    $("galleryChips")?.addEventListener("click", async (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      filter = btn.dataset.gfilter || "all";
      document.querySelectorAll("#galleryChips .chip").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      await fetchRows();
    });
    $("gallerySearch")?.addEventListener(
      "input",
      debounce((e) => {
        query = e.target.value.trim();
        visibleCount = pageSize;
        render();
      }, 160)
    );
    $("gallerySort")?.addEventListener("change", (e) => {
      const parts = String(e.target.value || "score:desc").split(":");
      sortKey = parts[0] === "scored" ? "scored" : "score";
      sortDir = parts[1] === "asc" ? "asc" : "desc";
      visibleCount = pageSize;
      render();
    });
    $("galleryPageSize")?.addEventListener("change", (e) => {
      pageSize = Math.max(12, Math.min(200, Number(e.target.value) || 48));
      visibleCount = pageSize;
      render();
    });
    $("galleryPrev")?.addEventListener("click", () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    $("galleryNext")?.addEventListener("click", () => revealMore());
    $("galleryRefresh")?.addEventListener("click", () => fetchRows());
    $("galleryGrid")?.addEventListener("click", onGridClick);
    document.addEventListener("keydown", onKey);
  }

  async function show() {
    if (!loaded) await fetchRows();
    else render();
    $("galleryGrid")?.focus({ preventScroll: true });
  }

  wire();

  return { show, refresh: fetchRows };
})();
