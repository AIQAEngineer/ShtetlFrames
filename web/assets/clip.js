function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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

const form = document.getElementById("clipForm");
const timesForm = document.getElementById("clipTimes");
const statusEl = document.getElementById("clipStatus");
const driveEl = document.getElementById("clipDriveStatus");
const resultEl = document.getElementById("clipResult");
const videoEl = document.getElementById("clipVideo");
const startEl = document.getElementById("clipStart");
const endEl = document.getElementById("clipEnd");
const nameEl = document.getElementById("clipName");
const metaEl = document.getElementById("clipMeta");
const doneEl = document.getElementById("clipDone");
const doneMeta = document.getElementById("clipDoneMeta");
const outEl = document.getElementById("clipOut");
const loadBtn = document.getElementById("clipLoad");
const uploadBtn = document.getElementById("clipUpload");

let loaded = null;
let lastTrim = null;
let busy = false;

function setBusy(on, label) {
  busy = on;
  loadBtn.disabled = on;
  uploadBtn.disabled = on;
  const cutBtn = document.getElementById("clipCut");
  if (cutBtn) cutBtn.disabled = on;
  if (label) statusEl.textContent = label;
}

async function refreshDriveStatus() {
  const authBtn = document.getElementById("clipDriveAuth");
  try {
    const r = await fetch("/api/clip/drive");
    const j = await r.json();
    const bits = [];
    if (j.configured) {
      bits.push(`Google Drive: folder ${j.folder_id} (${j.auth_mode || "creds"})`);
    } else {
      bits.push("Google Drive: not configured");
    }
    if (j.warning) {
      bits.push(j.warning);
      driveEl.classList.add("is-warn");
    } else if (j.hint) {
      bits.push(j.hint);
      driveEl.classList.toggle("is-warn", !j.configured || (j.auth_mode === "oauth" && !j.has_token));
    } else {
      driveEl.classList.remove("is-warn");
    }
    if (j.has_token) bits.push("signed in");
    else if (j.auth_mode === "oauth") bits.push("not signed in yet");
    driveEl.textContent = bits.join(" — ");
    if (authBtn) {
      authBtn.hidden = false;
      authBtn.textContent = j.has_token ? "Re-connect Google account" : "Connect Google account";
    }
    return j;
  } catch {
    driveEl.textContent = "Google Drive: status unavailable";
    return null;
  }
}

document.getElementById("clipDriveAuth")?.addEventListener("click", async () => {
  const btn = document.getElementById("clipDriveAuth");
  btn.disabled = true;
  statusEl.textContent = "Opening Google sign-in in a browser window…";
  try {
    const r = await fetch("/api/clip/drive/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const j = await r.json();
    if (!j.ok) {
      statusEl.textContent = `Sign-in failed: ${j.detail || j.error || r.status}`;
      return;
    }
    statusEl.textContent = "Google account connected.";
    await refreshDriveStatus();
  } catch (err) {
    statusEl.textContent = `Sign-in failed: ${err.message || err}`;
  } finally {
    btn.disabled = false;
  }
});

function range() {
  const start = parseTime(startEl.value);
  const end = parseTime(endEl.value);
  if (start == null || end == null) {
    return { error: "Enter start and end as seconds or m:ss (example: 14:02)" };
  }
  if (end <= start) {
    return { error: "End must be after start" };
  }
  return { start, end };
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = document.getElementById("clipUrl").value.trim();
  if (!url) return;
  setBusy(true, "Downloading / resolving video…");
  resultEl.hidden = true;
  doneEl.hidden = true;
  loaded = null;
  lastTrim = null;
  try {
    const r = await fetch("/api/clip/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const j = await r.json();
    if (!j.ok) {
      statusEl.textContent = `Load failed: ${j.error || r.status}`;
      return;
    }
    loaded = j;
    videoEl.src = `${j.media_url}?t=${Date.now()}`;
    if (!startEl.value) startEl.value = "0:00";
    nameEl.value = nameEl.value || `${j.video_id}_clip.mp4`;
    metaEl.textContent = `${j.video_id} · ${fmtBytes(j.bytes)}`;
    resultEl.hidden = false;
    statusEl.textContent = "Video ready — scrub, set start/end from the playhead, then upload.";
    videoEl.onloadedmetadata = () => {
      if (!endEl.value) endEl.value = fmtTime(Math.min(10, videoEl.duration || 10));
    };
  } catch (err) {
    statusEl.textContent = `Load failed: ${err.message || err}`;
  } finally {
    setBusy(false);
  }
});

document.getElementById("clipSetStart").addEventListener("click", () => {
  startEl.value = fmtTime(videoEl.currentTime || 0);
});

document.getElementById("clipSetEnd").addEventListener("click", () => {
  endEl.value = fmtTime(videoEl.currentTime || 0);
});

document.getElementById("clipPreview").addEventListener("click", () => {
  const r = range();
  if (r.error) {
    statusEl.textContent = r.error;
    return;
  }
  videoEl.currentTime = r.start;
  videoEl.play().catch(() => {});
  const stopAt = r.end;
  const onTime = () => {
    if (videoEl.currentTime >= stopAt) {
      videoEl.pause();
      videoEl.removeEventListener("timeupdate", onTime);
    }
  };
  videoEl.removeEventListener("timeupdate", onTime);
  videoEl.addEventListener("timeupdate", onTime);
  statusEl.textContent = `Previewing ${fmtTime(r.start)} → ${fmtTime(r.end)}`;
});

async function cutOnly() {
  if (!loaded) {
    statusEl.textContent = "Load a video first (click Load video).";
    return null;
  }
  const r = range();
  if (r.error) {
    statusEl.textContent = r.error;
    return null;
  }
  statusEl.textContent = "Cutting clip…";
  const res = await fetch("/api/clip/cut", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: document.getElementById("clipUrl").value.trim(),
      video_id: loaded.video_id,
      start: r.start,
      end: r.end,
    }),
  });
  const j = await res.json();
  if (!j.ok) {
    statusEl.textContent = `Cut failed: ${j.error || res.status}`;
    return null;
  }
  lastTrim = j;
  doneEl.hidden = false;
  outEl.hidden = false;
  outEl.src = `${j.media_url}?t=${Date.now()}`;
  doneMeta.innerHTML = `Local cut ready · ${fmtTime(j.start_sec)}–${fmtTime(j.end_sec)} · ${fmtBytes(
    j.bytes
  )} · <a href="${escapeHtml(j.media_url)}" download>Download</a>`;
  statusEl.textContent = "Cut ready.";
  return j;
}

document.getElementById("clipCut").addEventListener("click", async () => {
  if (busy) return;
  setBusy(true, "Cutting clip…");
  try {
    await cutOnly();
  } finally {
    setBusy(false);
  }
});

async function uploadToDrive() {
  if (!loaded) {
    statusEl.textContent = "Load a video first (click Load video).";
    return;
  }
  const r = range();
  if (r.error) {
    statusEl.textContent = r.error;
    return;
  }
  const drive = await refreshDriveStatus();
  if (drive && drive.auth_mode === "oauth" && !drive.has_token) {
    statusEl.textContent = "Connect Google account first, then upload.";
    return;
  }

  setBusy(true, "Cutting and uploading to Google Drive… (can take a minute)");
  const body = {
    url: document.getElementById("clipUrl").value.trim(),
    video_id: loaded.video_id,
    start: r.start,
    end: r.end,
    name: nameEl.value.trim() || undefined,
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
    const res = await fetch("/api/clip/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let j;
    try {
      j = await res.json();
    } catch {
      statusEl.textContent = `Upload failed: bad response (${res.status})`;
      return;
    }
    if (!j.ok) {
      statusEl.textContent = `Upload failed: ${j.error || res.status}${
        j.hint ? ` — ${j.hint}` : j.detail ? ` — ${j.detail}` : ""
      }`;
      return;
    }
    lastTrim = j;
    doneEl.hidden = false;
    outEl.hidden = false;
    outEl.src = `${j.media_url}?t=${Date.now()}`;
    const link = j.drive?.webViewLink
      ? `<a href="${escapeHtml(j.drive.webViewLink)}" target="_blank" rel="noopener">Open in Drive</a>`
      : "uploaded";
    doneMeta.innerHTML = `Uploaded · ${fmtBytes(j.bytes)} · ${link}`;
    statusEl.textContent = "Uploaded to Google Drive.";
  } catch (err) {
    statusEl.textContent = `Upload failed: ${err.message || err}`;
  } finally {
    setBusy(false);
  }
}

uploadBtn.type = "button";
uploadBtn.addEventListener("click", (e) => {
  e.preventDefault();
  if (busy) {
    statusEl.textContent = "Already working — wait for cut/upload to finish.";
    return;
  }
  uploadToDrive();
});

timesForm.addEventListener("submit", (e) => {
  e.preventDefault();
  if (busy) return;
  uploadToDrive();
});

// Deep-link: /clip?url=...&start=...&end=...
(function initFromQuery() {
  const q = new URLSearchParams(location.search);
  const url = q.get("url");
  if (url) document.getElementById("clipUrl").value = url;
  if (q.get("start")) startEl.value = q.get("start");
  if (q.get("end")) endEl.value = q.get("end");
  if (url) form.requestSubmit();
})();

uploadBtn.disabled = false;
refreshDriveStatus();
