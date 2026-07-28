function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

function fmtTime(sec) {
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

const form = document.getElementById("markForm");
const statusEl = document.getElementById("markStatus");
const resultEl = document.getElementById("markResult");
const stripEl = document.getElementById("markStrip");
const framesEl = document.getElementById("markFrames");
const metaEl = document.getElementById("markMeta");
const hintEl = document.getElementById("markHint");
const goBtn = document.getElementById("markGo");
const combineBtn = document.getElementById("markCombine");
const hqEl = document.getElementById("markHq");
const hqImg = document.getElementById("markHqImg");
const hqMeta = document.getElementById("markHqMeta");

let lastPayload = null;

function selectedTimes() {
  return [...framesEl.querySelectorAll(".mark-frame.is-selected")]
    .map((el) => Number(el.dataset.time))
    .filter((t) => Number.isFinite(t));
}

function syncCombineUi() {
  const n = selectedTimes().length;
  combineBtn.disabled = n < 2;
  combineBtn.textContent = n < 2 ? "Stitch strip" : `Stitch strip (${n})`;
  if (hintEl) {
    hintEl.textContent =
      n < 2
        ? "Select at least 2 frames, then stitch them side by side at full resolution."
        : `${n} frames selected — stitch places them one after another at full resolution.`;
  }
}

function renderFrames(frames, bust) {
  const mark = Number(lastPayload?.mark_sec || 0);
  framesEl.innerHTML = (frames || [])
    .map((f, i) => {
      const near =
        Math.abs(Number(f.time_sec) - mark) <= 0.09 || Boolean(f.is_mark);
      const on = near;
      return `<figure class="mark-frame${on ? " is-selected" : ""}${f.is_mark ? " is-mark" : ""}" data-time="${escapeAttr(f.time_sec)}" tabindex="0" role="checkbox" aria-checked="${on ? "true" : "false"}">
          <img src="${escapeAttr(f.url)}${bust}" alt="${escapeAttr(f.label)}" draggable="false" />
          <figcaption>${escapeHtml(f.label)} · ${fmtTime(f.time_sec)}</figcaption>
          <span class="mark-pick">${on ? "Selected" : "Click to select"}</span>
        </figure>`;
    })
    .join("");
  syncCombineUi();
}

framesEl.addEventListener("click", (e) => {
  const fig = e.target.closest(".mark-frame");
  if (!fig || !framesEl.contains(fig)) return;
  fig.classList.toggle("is-selected");
  fig.setAttribute("aria-checked", fig.classList.contains("is-selected") ? "true" : "false");
  const pick = fig.querySelector(".mark-pick");
  if (pick) {
    pick.textContent = fig.classList.contains("is-selected")
      ? "Selected"
      : "Click to select";
  }
  syncCombineUi();
});

framesEl.addEventListener("keydown", (e) => {
  if (e.key !== " " && e.key !== "Enter") return;
  const fig = e.target.closest(".mark-frame");
  if (!fig) return;
  e.preventDefault();
  fig.click();
});

document.getElementById("markSelectAll").addEventListener("click", () => {
  framesEl.querySelectorAll(".mark-frame").forEach((fig) => {
    fig.classList.add("is-selected");
    fig.setAttribute("aria-checked", "true");
    const pick = fig.querySelector(".mark-pick");
    if (pick) pick.textContent = "Selected";
  });
  syncCombineUi();
});

document.getElementById("markSelectNone").addEventListener("click", () => {
  framesEl.querySelectorAll(".mark-frame").forEach((fig) => {
    fig.classList.remove("is-selected");
    fig.setAttribute("aria-checked", "false");
    const pick = fig.querySelector(".mark-pick");
    if (pick) pick.textContent = "Click to select";
  });
  syncCombineUi();
});

document.getElementById("markSelectMark").addEventListener("click", () => {
  const mark = Number(lastPayload?.mark_sec || 0);
  framesEl.querySelectorAll(".mark-frame").forEach((fig) => {
    const t = Number(fig.dataset.time);
    const on = Number.isFinite(t) && Math.abs(t - mark) <= 0.09;
    fig.classList.toggle("is-selected", on);
    fig.setAttribute("aria-checked", on ? "true" : "false");
    const pick = fig.querySelector(".mark-pick");
    if (pick) pick.textContent = on ? "Selected" : "Click to select";
  });
  syncCombineUi();
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = document.getElementById("markUrl").value.trim();
  const mark = document.getElementById("markSec").value.trim();
  if (!url || !mark) return;

  goBtn.disabled = true;
  combineBtn.disabled = true;
  statusEl.textContent = "Resolving Pathé + extracting frames… (first run may download the clip)";
  resultEl.hidden = true;
  hqEl.hidden = true;
  lastPayload = null;

  try {
    const res = await fetch("/api/mark", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, mark }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      statusEl.textContent =
        data.error || data.hint || `Failed (HTTP ${res.status})`;
      return;
    }

    lastPayload = data;
    const bust = `?t=${Date.now()}`;
    stripEl.src = `${data.strip_url}${bust}`;
    renderFrames(data.frames || [], bust);

    metaEl.innerHTML = `Asset <a href="${escapeAttr(data.source_url)}" target="_blank" rel="noopener">${escapeHtml(
      data.asset_id
    )}</a> · mark ${fmtTime(data.mark_sec)} · ${(data.frames || []).length} frames · strip ${fmtBytes(data.strip_bytes)}
      · <a href="${escapeAttr(data.strip_url)}" download>Download strip</a>`;

    statusEl.textContent = `Ready — pick frames around ${fmtTime(data.mark_sec)}, then Stitch strip`;
    resultEl.hidden = false;
  } catch (err) {
    statusEl.textContent = String(err?.message || err || "request failed");
  } finally {
    goBtn.disabled = false;
    syncCombineUi();
  }
});

combineBtn.addEventListener("click", async () => {
  if (!lastPayload) return;
  const times = selectedTimes();
  if (times.length < 2) return;
  const url =
    document.getElementById("markUrl").value.trim() || lastPayload.source_url;

  combineBtn.disabled = true;
  goBtn.disabled = true;
  statusEl.textContent = `Stitching ${times.length} frames at full resolution…`;

  try {
    const res = await fetch("/api/mark/combine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        mark: lastPayload.mark_sec,
        times,
        scale: 1,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      statusEl.textContent =
        data.error || data.hint || `Stitch failed (HTTP ${res.status})`;
      return;
    }

    const bust = `?t=${Date.now()}`;
    hqImg.src = `${data.hq_url}${bust}`;
    const pngBit = data.hq_png_url
      ? ` · <a href="${escapeAttr(data.hq_png_url)}" download>Download PNG</a>`
      : "";
    hqMeta.innerHTML = `${data.width}×${data.height} · ${data.frame_count} frames side-by-side · ${fmtBytes(data.hq_bytes)}
      · <a href="${escapeAttr(data.hq_url)}" download>Download JPEG</a>${pngBit}`;
    hqEl.hidden = false;
    statusEl.textContent = `Strip ready — ${data.frame_count} frames · ${data.width}×${data.height}`;
    hqEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    statusEl.textContent = String(err?.message || err || "stitch failed");
  } finally {
    goBtn.disabled = false;
    syncCombineUi();
  }
});
