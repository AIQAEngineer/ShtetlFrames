function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtTime(sec) {
  if (sec == null || !Number.isFinite(Number(sec))) return "";
  const n = Math.max(0, Number(sec));
  const s = Math.floor(n);
  const m = Math.floor(s / 60);
  const r = s % 60;
  const frac = Math.round((n - s) * 100);
  const base = `${m}:${String(r).padStart(2, "0")}`;
  return frac ? `${base}.${String(frac).padStart(2, "0")}` : base;
}

const grid = document.getElementById("probeGrid");
const statusEl = document.getElementById("probeStatus");
const statsEl = document.getElementById("probeStats");
const pager = document.getElementById("probePager");
const pageLabel = document.getElementById("probePageLabel");

let label = "all";
let status = "all";
let offset = 0;
const limit = 120;
let lastItems = [];
let busy = false;

function setChipGroup(rowId, attr, value) {
  document.querySelectorAll(`#${rowId} .chip`).forEach((btn) => {
    btn.classList.toggle("active", btn.dataset[attr] === value);
  });
}

async function loadFrames() {
  statusEl.textContent = "Loading frames…";
  const qs = new URLSearchParams({
    label,
    status,
    limit: String(limit),
    offset: String(offset),
  });
  try {
    const r = await fetch(`/api/clip_ft/frames?${qs}`);
    const j = await r.json();
    if (!j.ok) {
      statusEl.textContent = `Load failed: ${j.error || r.status}`;
      return;
    }
    lastItems = j.items || [];
    const c = j.counts || {};
    statsEl.textContent =
      `Train as good: ${c.keep_included ?? 0} Keep · ` +
      `Train as wrong: ${(c.pass_included ?? 0) + (c.excluded ?? 0)} ` +
      `(${c.pass_included ?? 0} Pass included + ${c.excluded ?? 0} excluded) · ` +
      `on disk Keep ${c.keep ?? 0} / Pass ${c.pass ?? 0}`;
    render(lastItems);
    const total = Number(j.total) || 0;
    const start = total ? offset + 1 : 0;
    const end = Math.min(offset + lastItems.length, total);
    statusEl.textContent = total
      ? `Showing ${start}–${end} of ${total}`
      : "No frames in dataset — run deep CLIP export first.";
    pager.hidden = total <= limit;
    pageLabel.textContent = `${start}–${end} / ${total}`;
    document.getElementById("probePrev").disabled = offset <= 0;
    document.getElementById("probeNext").disabled = offset + limit >= total;
  } catch (err) {
    statusEl.textContent = `Load failed: ${err.message || err}`;
  }
}

function render(items) {
  grid.innerHTML = items
    .map((it) => {
      const on = it.included;
      const meta = [
        it.label,
        it.cand_id != null ? `#${it.cand_id}` : null,
        it.time_sec != null ? fmtTime(it.time_sec) : it.name.includes("_still") ? "still" : null,
      ]
        .filter(Boolean)
        .join(" · ");
      return `<figure class="probe-card${on ? " is-in" : " is-out"}" data-path="${escapeHtml(
        it.path
      )}" tabindex="0" role="button" aria-pressed="${on ? "true" : "false"}">
        <img src="${escapeHtml(it.url)}" alt="${escapeHtml(it.path)}" loading="lazy" />
        <figcaption>${escapeHtml(meta)}</figcaption>
        <span class="probe-flag">${on ? "Included · good if Keep" : "Excluded · trains as wrong"}</span>
      </figure>`;
    })
    .join("");
}

async function setExcluded(paths, excluded) {
  if (!paths.length || busy) return;
  busy = true;
  try {
    const r = await fetch("/api/clip_ft/exclude", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths, excluded }),
    });
    const j = await r.json();
    if (!j.ok) {
      statusEl.textContent = `Update failed: ${j.error || r.status}`;
      return;
    }
    await loadFrames();
  } catch (err) {
    statusEl.textContent = `Update failed: ${err.message || err}`;
  } finally {
    busy = false;
  }
}

grid.addEventListener("click", (e) => {
  const card = e.target.closest(".probe-card");
  if (!card) return;
  const path = card.dataset.path;
  const item = lastItems.find((x) => x.path === path);
  if (!item) return;
  setExcluded([path], item.included); // toggle → exclude if currently included
});

grid.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const card = e.target.closest(".probe-card");
  if (!card) return;
  e.preventDefault();
  card.click();
});

document.getElementById("labelChips").addEventListener("click", (e) => {
  const btn = e.target.closest(".chip");
  if (!btn) return;
  label = btn.dataset.label || "all";
  offset = 0;
  setChipGroup("labelChips", "label", label);
  loadFrames();
});

document.getElementById("statusChips").addEventListener("click", (e) => {
  const btn = e.target.closest(".chip");
  if (!btn) return;
  status = btn.dataset.status || "all";
  offset = 0;
  setChipGroup("statusChips", "status", status);
  loadFrames();
});

document.getElementById("probeIncludeAll").addEventListener("click", () => {
  setExcluded(
    lastItems.map((i) => i.path),
    false
  );
});

document.getElementById("probeExcludeAll").addEventListener("click", () => {
  setExcluded(
    lastItems.map((i) => i.path),
    true
  );
});

document.getElementById("probePrev").addEventListener("click", () => {
  offset = Math.max(0, offset - limit);
  loadFrames();
});

document.getElementById("probeNext").addEventListener("click", () => {
  offset += limit;
  loadFrames();
});

document.getElementById("probeTrain").addEventListener("click", async () => {
  const btn = document.getElementById("probeTrain");
  btn.disabled = true;
  statusEl.textContent = "Starting CLIP train from included frames…";
  try {
    const r = await fetch("/api/train/clip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ export: false, deep: false }),
    });
    const j = await r.json();
    if (!j.ok) {
      statusEl.textContent = `Train failed: ${j.error || r.status}`;
      return;
    }
    statusEl.textContent =
      "CLIP training started — uses currently included frames only (deep export not re-run). Watch /train or job clip_ft.";
  } catch (err) {
    statusEl.textContent = `Train failed: ${err.message || err}`;
  } finally {
    btn.disabled = false;
  }
});

loadFrames();
