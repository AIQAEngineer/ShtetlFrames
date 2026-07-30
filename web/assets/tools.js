/* Tools hub: Mark & stitch (frame strips) + Cut & upload (Drive clips). */

/* —— Mark & stitch —— */

const markForm = $("markForm");
const markStatus = $("markStatus");
const markResult = $("markResult");
const markStrip = $("markStrip");
const markFrames = $("markFrames");
const markMeta = $("markMeta");
const markHint = $("markHint");
const markGo = $("markGo");
const markCombine = $("markCombine");
const markHq = $("markHq");
const markHqImg = $("markHqImg");
const markHqMeta = $("markHqMeta");

let lastMarkPayload = null;

function selectedTimes() {
  return [...markFrames.querySelectorAll(".frame-card.is-selected")]
    .map((el) => Number(el.dataset.time))
    .filter((t) => Number.isFinite(t));
}

function syncCombineUi() {
  const n = selectedTimes().length;
  markCombine.disabled = n < 2;
  markCombine.textContent = n < 2 ? "Stitch strip" : `Stitch strip (${n})`;
  if (markHint) {
    markHint.textContent =
      n < 2
        ? "Select at least 2 frames, then stitch them side by side at full resolution."
        : `${n} frames selected — stitch places them one after another at full resolution.`;
  }
}

function setFrameSelected(fig, on) {
  fig.classList.toggle("is-selected", on);
  fig.setAttribute("aria-checked", on ? "true" : "false");
  const pick = fig.querySelector(".frame-flag");
  if (pick) pick.textContent = on ? "Selected" : "Click to select";
}

function renderMarkFrames(frames, bust) {
  const mark = Number(lastMarkPayload?.mark_sec || 0);
  markFrames.innerHTML = (frames || [])
    .map((f) => {
      const near =
        Math.abs(Number(f.time_sec) - mark) <= 0.09 || Boolean(f.is_mark);
      return `<figure class="frame-card${near ? " is-selected" : ""}${f.is_mark ? " is-mark" : ""}" data-time="${escapeAttr(f.time_sec)}" tabindex="0" role="checkbox" aria-checked="${near ? "true" : "false"}">
          <img src="${escapeAttr(f.url)}${bust}" alt="${escapeAttr(f.label)}" draggable="false" />
          <figcaption>${escapeHtml(f.label)} · ${fmtTimeFrac(f.time_sec)}</figcaption>
          <span class="frame-flag">${near ? "Selected" : "Click to select"}</span>
        </figure>`;
    })
    .join("");
  syncCombineUi();
}

markFrames.addEventListener("click", (e) => {
  const fig = e.target.closest(".frame-card");
  if (!fig || !markFrames.contains(fig)) return;
  setFrameSelected(fig, !fig.classList.contains("is-selected"));
  syncCombineUi();
});

markFrames.addEventListener("keydown", (e) => {
  if (e.key !== " " && e.key !== "Enter") return;
  const fig = e.target.closest(".frame-card");
  if (!fig) return;
  e.preventDefault();
  fig.click();
});

$("markSelectAll").addEventListener("click", () => {
  markFrames.querySelectorAll(".frame-card").forEach((fig) => setFrameSelected(fig, true));
  syncCombineUi();
});

$("markSelectNone").addEventListener("click", () => {
  markFrames.querySelectorAll(".frame-card").forEach((fig) => setFrameSelected(fig, false));
  syncCombineUi();
});

$("markSelectMark").addEventListener("click", () => {
  const mark = Number(lastMarkPayload?.mark_sec || 0);
  markFrames.querySelectorAll(".frame-card").forEach((fig) => {
    const t = Number(fig.dataset.time);
    setFrameSelected(fig, Number.isFinite(t) && Math.abs(t - mark) <= 0.09);
  });
  syncCombineUi();
});

markForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = $("markUrl").value.trim();
  const mark = $("markSec").value.trim();
  if (!url || !mark) return;

  markGo.disabled = true;
  markCombine.disabled = true;
  markStatus.textContent = "Resolving Pathé + extracting frames… (first run may download the clip)";
  markResult.hidden = true;
  markHq.hidden = true;
  lastMarkPayload = null;

  try {
    const data = await apiPost("/api/mark", { url, mark });
    if (!data.ok) {
      markStatus.textContent =
        data.error || data.hint || `Failed (HTTP ${data.status})`;
      return;
    }

    lastMarkPayload = data;
    const bust = `?t=${Date.now()}`;
    markStrip.src = `${data.strip_url}${bust}`;
    renderMarkFrames(data.frames || [], bust);

    markMeta.innerHTML = `Asset <a href="${escapeAttr(data.source_url)}" target="_blank" rel="noopener">${escapeHtml(
      data.asset_id
    )}</a> · mark ${fmtTimeFrac(data.mark_sec)} · ${(data.frames || []).length} frames · strip ${fmtBytes(data.strip_bytes)}
      · <a href="${escapeAttr(data.strip_url)}" download>Download strip</a>`;

    markStatus.textContent = `Ready — pick frames around ${fmtTimeFrac(data.mark_sec)}, then Stitch strip`;
    markResult.hidden = false;
  } catch (err) {
    markStatus.textContent = String(err?.message || err || "request failed");
  } finally {
    markGo.disabled = false;
    syncCombineUi();
  }
});

markCombine.addEventListener("click", async () => {
  if (!lastMarkPayload) return;
  const times = selectedTimes();
  if (times.length < 2) return;
  const url =
    $("markUrl").value.trim() || lastMarkPayload.source_url;

  markCombine.disabled = true;
  markGo.disabled = true;
  markStatus.textContent = `Stitching ${times.length} frames at full resolution…`;

  try {
    const data = await apiPost("/api/mark/combine", {
      url,
      mark: lastMarkPayload.mark_sec,
      times,
      scale: 1,
    });
    if (!data.ok) {
      markStatus.textContent =
        data.error || data.hint || `Stitch failed (HTTP ${data.status})`;
      return;
    }

    const bust = `?t=${Date.now()}`;
    markHqImg.src = `${data.hq_url}${bust}`;
    const pngBit = data.hq_png_url
      ? ` · <a href="${escapeAttr(data.hq_png_url)}" download>Download PNG</a>`
      : "";
    markHqMeta.innerHTML = `${data.width}×${data.height} · ${data.frame_count} frames side-by-side · ${fmtBytes(data.hq_bytes)}
      · <a href="${escapeAttr(data.hq_url)}" download>Download JPEG</a>${pngBit}`;
    markHq.hidden = false;
    markStatus.textContent = `Strip ready — ${data.frame_count} frames · ${data.width}×${data.height}`;
    markHq.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    markStatus.textContent = String(err?.message || err || "stitch failed");
  } finally {
    markGo.disabled = false;
    syncCombineUi();
  }
});

/* —— Cut & upload —— */

function parseTime(raw) {
  const s = String(raw ?? "").trim().replace(",", ".");
  if (!s) return null;
  if (s.includes(":")) {
    const parts = s.split(":").map((p) => Number(p));
    if (parts.some((n) => !Number.isFinite(n))) return null;
    if (parts.length === 2) return Math.max(0, parts[0] * 60 + parts[1]);
    if (parts.length === 3) return Math.max(0, parts[0] * 3600 + parts[1] * 60 + parts[2]);
    return null;
  }
  const n = Number(s);
  return Number.isFinite(n) ? Math.max(0, n) : null;
}

const clipForm = $("clipForm");
const clipTimes = $("clipTimes");
const clipStatus = $("clipStatus");
const clipDriveStatus = $("clipDriveStatus");
const clipResult = $("clipResult");
const clipVideo = $("clipVideo");
const clipStart = $("clipStart");
const clipEnd = $("clipEnd");
const clipName = $("clipName");
const clipMeta = $("clipMeta");
const clipDone = $("clipDone");
const clipDoneMeta = $("clipDoneMeta");
const clipOut = $("clipOut");
const clipLoad = $("clipLoad");
const clipUpload = $("clipUpload");

let clipLoaded = null;
let lastTrim = null;
let clipBusy = false;

function setClipBusy(on, label) {
  clipBusy = on;
  clipLoad.disabled = on;
  clipUpload.disabled = on;
  const cutBtn = $("clipCut");
  if (cutBtn) cutBtn.disabled = on;
  if (label) clipStatus.textContent = label;
}

async function refreshDriveStatus() {
  const authBtn = $("clipDriveAuth");
  try {
    const j = await apiGet("/api/clip/drive");
    const bits = [];
    if (j.configured) {
      bits.push(`Google Drive: folder ${j.folder_id} (${j.auth_mode || "creds"})`);
    } else {
      bits.push("Google Drive: not configured");
    }
    if (j.warning) {
      bits.push(j.warning);
      clipDriveStatus.classList.add("is-warn");
    } else if (j.hint) {
      bits.push(j.hint);
      clipDriveStatus.classList.toggle("is-warn", !j.configured || (j.auth_mode === "oauth" && !j.has_token));
    } else {
      clipDriveStatus.classList.remove("is-warn");
    }
    if (j.has_token) bits.push("signed in");
    else if (j.auth_mode === "oauth") bits.push("not signed in yet");
    clipDriveStatus.textContent = bits.join(" — ");
    if (authBtn) {
      authBtn.hidden = false;
      authBtn.textContent = j.has_token ? "Re-connect Google account" : "Connect Google account";
    }
    return j;
  } catch {
    clipDriveStatus.textContent = "Google Drive: status unavailable";
    return null;
  }
}

$("clipDriveAuth")?.addEventListener("click", async () => {
  const btn = $("clipDriveAuth");
  btn.disabled = true;
  clipStatus.textContent = "Opening Google sign-in in a browser window…";
  try {
    const j = await apiPost("/api/clip/drive/auth", {});
    if (!j.ok) {
      clipStatus.textContent = `Sign-in failed: ${j.detail || j.error || j.status}`;
      return;
    }
    clipStatus.textContent = "Google account connected.";
    await refreshDriveStatus();
  } catch (err) {
    clipStatus.textContent = `Sign-in failed: ${err.message || err}`;
  } finally {
    btn.disabled = false;
  }
});

function clipRange() {
  const start = parseTime(clipStart.value);
  const end = parseTime(clipEnd.value);
  if (start == null || end == null) {
    return { error: "Enter start and end as seconds or m:ss (example: 14:02)" };
  }
  if (end <= start) {
    return { error: "End must be after start" };
  }
  return { start, end };
}

clipForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = $("clipUrl").value.trim();
  if (!url) return;
  setClipBusy(true, "Downloading / resolving video…");
  clipResult.hidden = true;
  clipDone.hidden = true;
  clipLoaded = null;
  lastTrim = null;
  try {
    const j = await apiPost("/api/clip/load", { url });
    if (!j.ok) {
      clipStatus.textContent = `Load failed: ${j.error || j.status}`;
      return;
    }
    clipLoaded = j;
    clipVideo.src = `${j.media_url}?t=${Date.now()}`;
    if (!clipStart.value) clipStart.value = "0:00";
    clipName.value = clipName.value || `${j.video_id}_clip.mp4`;
    clipMeta.textContent = `${j.video_id} · ${fmtBytes(j.bytes)}`;
    clipResult.hidden = false;
    clipStatus.textContent = "Video ready — scrub, set start/end from the playhead, then upload.";
    clipVideo.onloadedmetadata = () => {
      if (!clipEnd.value) clipEnd.value = fmtTimeFrac(Math.min(10, clipVideo.duration || 10));
    };
  } catch (err) {
    clipStatus.textContent = `Load failed: ${err.message || err}`;
  } finally {
    setClipBusy(false);
  }
});

$("clipSetStart").addEventListener("click", () => {
  clipStart.value = fmtTimeFrac(clipVideo.currentTime || 0);
});

$("clipSetEnd").addEventListener("click", () => {
  clipEnd.value = fmtTimeFrac(clipVideo.currentTime || 0);
});

$("clipPreview").addEventListener("click", () => {
  const r = clipRange();
  if (r.error) {
    clipStatus.textContent = r.error;
    return;
  }
  clipVideo.currentTime = r.start;
  clipVideo.play().catch(() => {});
  const stopAt = r.end;
  const onTime = () => {
    if (clipVideo.currentTime >= stopAt) {
      clipVideo.pause();
      clipVideo.removeEventListener("timeupdate", onTime);
    }
  };
  clipVideo.removeEventListener("timeupdate", onTime);
  clipVideo.addEventListener("timeupdate", onTime);
  clipStatus.textContent = `Previewing ${fmtTimeFrac(r.start)} → ${fmtTimeFrac(r.end)}`;
});

async function cutOnly() {
  if (!clipLoaded) {
    clipStatus.textContent = "Load a video first (click Load video).";
    return null;
  }
  const r = clipRange();
  if (r.error) {
    clipStatus.textContent = r.error;
    return null;
  }
  clipStatus.textContent = "Cutting clip…";
  const j = await apiPost("/api/clip/cut", {
    url: $("clipUrl").value.trim(),
    video_id: clipLoaded.video_id,
    start: r.start,
    end: r.end,
  });
  if (!j.ok) {
    clipStatus.textContent = `Cut failed: ${j.error || j.status}`;
    return null;
  }
  lastTrim = j;
  clipDone.hidden = false;
  clipOut.hidden = false;
  clipOut.src = `${j.media_url}?t=${Date.now()}`;
  clipDoneMeta.innerHTML = `Local cut ready · ${fmtTimeFrac(j.start_sec)}–${fmtTimeFrac(j.end_sec)} · ${fmtBytes(
    j.bytes
  )} · <a href="${escapeAttr(j.media_url)}" download>Download</a>`;
  clipStatus.textContent = "Cut ready.";
  return j;
}

$("clipCut").addEventListener("click", async () => {
  if (clipBusy) return;
  setClipBusy(true, "Cutting clip…");
  try {
    await cutOnly();
  } finally {
    setClipBusy(false);
  }
});

async function uploadToDrive() {
  if (!clipLoaded) {
    clipStatus.textContent = "Load a video first (click Load video).";
    return;
  }
  const r = clipRange();
  if (r.error) {
    clipStatus.textContent = r.error;
    return;
  }
  const drive = await refreshDriveStatus();
  if (drive && drive.auth_mode === "oauth" && !drive.has_token) {
    clipStatus.textContent = "Connect Google account first, then upload.";
    return;
  }

  setClipBusy(true, "Cutting and uploading to Google Drive… (can take a minute)");
  const body = {
    url: $("clipUrl").value.trim(),
    video_id: clipLoaded.video_id,
    start: r.start,
    end: r.end,
    name: clipName.value.trim() || undefined,
  };
  // Only reuse a trim we know we already cut this session
  if (
    lastTrim?.file &&
    Number(lastTrim.start_sec) === r.start &&
    Number(lastTrim.end_sec) === r.end
  ) {
    body.file = lastTrim.file;
  }

  try {
    const j = await apiPost("/api/clip/upload", body);
    if (!j.ok) {
      clipStatus.textContent = `Upload failed: ${j.error || j.status}${
        j.hint ? ` — ${j.hint}` : j.detail ? ` — ${j.detail}` : ""
      }`;
      return;
    }
    lastTrim = j;
    clipDone.hidden = false;
    clipOut.hidden = false;
    clipOut.src = `${j.media_url}?t=${Date.now()}`;
    const link = j.drive?.webViewLink
      ? `<a href="${escapeAttr(j.drive.webViewLink)}" target="_blank" rel="noopener">Open in Drive</a>`
      : "uploaded";
    clipDoneMeta.innerHTML = `Uploaded · ${fmtBytes(j.bytes)} · ${link}`;
    clipStatus.textContent = "Uploaded to Google Drive.";
  } catch (err) {
    clipStatus.textContent = `Upload failed: ${err.message || err}`;
  } finally {
    setClipBusy(false);
  }
}

clipUpload.type = "button";
clipUpload.addEventListener("click", (e) => {
  e.preventDefault();
  if (clipBusy) {
    clipStatus.textContent = "Already working — wait for cut/upload to finish.";
    return;
  }
  uploadToDrive();
});

clipTimes.addEventListener("submit", (e) => {
  e.preventDefault();
  if (clipBusy) return;
  uploadToDrive();
});

/* Deep-link: /tools?tab=clip&url=...&start=...&end=... */
(function initFromQuery() {
  const q = new URLSearchParams(location.search);
  const url = q.get("url");
  if (url) $("clipUrl").value = url;
  if (q.get("start")) clipStart.value = q.get("start");
  if (q.get("end")) clipEnd.value = q.get("end");
  if (url) clipForm.requestSubmit();
})();

clipUpload.disabled = false;
refreshDriveStatus();

renderNav("tools");
initTabs("mark");
