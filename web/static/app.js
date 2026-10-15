let sessionId = null;
let videos = [];
let lastSelCount = 0;

// ── FETCH ──────────────────────────────────────────────────────────────────

async function onFetch() {
  const url = document.getElementById("urlInput").value.trim();
  if (!url) { alert("Please enter a YouTube URL."); return; }

  setStatus("Fetching playlist info…");
  setBusy(true);
  clearList();

  try {
    const res = await fetch("/api/fetch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    sessionId = data.session_id;
    videos = data.videos;
    renderList(videos);
    setStatus(`Found ${videos.length} video(s)`, "var(--success)");
  } catch (e) {
    setStatus("Error: " + e.message, "var(--error)");
  } finally {
    setBusy(false);
  }
}

// ── RENDER ─────────────────────────────────────────────────────────────────

function renderList(vids) {
  const list = document.getElementById("videoList");
  list.innerHTML = "";
  document.getElementById("listHeader").style.display = vids.length ? "flex" : "none";

  if (!vids.length) {
    list.innerHTML = '<p class="empty-msg">No videos found.</p>';
    return;
  }

  vids.forEach((v, i) => {
    const row = document.createElement("div");
    row.className = "video-row";
    row.id = `row-${i}`;
    row.innerHTML = `
      <input type="checkbox" checked style="accent-color:var(--accent);width:18px;height:18px" id="chk-${i}" />
      <span class="num">${String(i + 1).padStart(2, "0")}</span>
      <span class="title" title="${esc(v.title)}">${esc(v.title.slice(0, 80))}</span>
      <span class="dur">${v.duration}</span>
      <span class="size" id="size-${i}">—</span>
      <span class="stat" id="stat-${i}"></span>
      <div class="row-progress" id="prog-${i}">
        <div class="row-progress-fill" id="progfill-${i}" style="width:0%"></div>
      </div>`;
    list.appendChild(row);
  });

  document.getElementById("estimateBtn").disabled = false;
  document.getElementById("dlBtn").disabled = false;
}

function clearList() {
  const list = document.getElementById("videoList");
  list.innerHTML = '<p class="empty-msg">Paste a YouTube URL and click Fetch</p>';
  document.getElementById("listHeader").style.display = "none";
  document.getElementById("estimateBtn").disabled = true;
  document.getElementById("dlBtn").disabled = true;
  document.getElementById("totalLabel").textContent = "";
  document.getElementById("overallFill").style.width = "0%";
}

// ── SELECT ALL ─────────────────────────────────────────────────────────────

function toggleAll() {
  const val = document.getElementById("selectAll").checked;
  videos.forEach((_, i) => {
    const chk = document.getElementById(`chk-${i}`);
    if (chk) chk.checked = val;
  });
}

function getSelected() {
  return videos.map((_, i) => i).filter(i => {
    const chk = document.getElementById(`chk-${i}`);
    return chk && chk.checked;
  });
}

// ── ESTIMATE ───────────────────────────────────────────────────────────────

async function onEstimate() {
  const sel = getSelected();
  if (!sel.length) { alert("Select at least one video."); return; }

  setStatus("Estimating size…");
  setBusy(true);

  try {
    const res = await fetch("/api/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        indices: sel,
        quality: document.getElementById("qualitySelect").value,
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    Object.entries(data.sizes).forEach(([i, s]) => {
      const el = document.getElementById(`size-${i}`);
      if (el) el.textContent = s;
    });
    document.getElementById("totalLabel").textContent = "Total: " + data.total;
    setStatus("Estimation complete ✔", "var(--success)");
  } catch (e) {
    setStatus("Error: " + e.message, "var(--error)");
  } finally {
    setBusy(false);
  }
}

// ── DOWNLOAD ───────────────────────────────────────────────────────────────

async function onDownload() {
  const sel = getSelected();
  if (!sel.length) { alert("Select at least one video."); return; }

  lastSelCount = sel.length;
  setStatus("Starting download…");
  setBusy(true, true);
  setOverall(0);

  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        indices: sel,
        quality: document.getElementById("qualitySelect").value,
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    listenProgress(data.job_id);
  } catch (e) {
    setStatus("Error: " + e.message, "var(--error)");
    setBusy(false);
  }
}

function listenProgress(jobId) {
  const es = new EventSource(`/api/progress/${jobId}`);

  es.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === "start") {
      const stat = document.getElementById(`stat-${msg.index}`);
      if (stat) stat.innerHTML = `<span style="color:var(--accent)">⬇ Downloading…</span>`;
      const bar = document.getElementById(`prog-${msg.index}`);
      if (bar) bar.style.display = "block";
    }

    if (msg.type === "progress") {
      const fill = document.getElementById(`progfill-${msg.index}`);
      if (fill) fill.style.width = (msg.pct * 100).toFixed(1) + "%";
      const stat = document.getElementById(`stat-${msg.index}`);
      if (stat) stat.innerHTML =
        `<span style="color:var(--accent)">${(msg.pct * 100).toFixed(0)}% ${msg.speed}</span>`;
    }

    if (msg.type === "done_one") {
      const fill = document.getElementById(`progfill-${msg.index}`);
      if (fill) fill.style.width = "100%";
      const stat = document.getElementById(`stat-${msg.index}`);
      if (stat) {
        const link = msg.file
          ? `<a class="dl-link" href="/downloads/${encodeURIComponent(msg.file)}" download>⬇ Save</a>`
          : "";
        stat.innerHTML = `<span style="color:var(--success)">✔ Done ${link}</span>`;
      }
      setOverall(msg.overall);
      const done = Math.round(msg.overall * lastSelCount);
      setStatus(`Downloaded ${done} / ${lastSelCount}`);
    }

    if (msg.type === "error") {
      const stat = document.getElementById(`stat-${msg.index}`);
      if (stat) stat.innerHTML = `<span style="color:var(--error)">✘ Error</span>`;
    }

    if (msg.type === "done") {
      setOverall(1);
      setStatus("All done! 🎉", "var(--success)");
      setBusy(false);
      es.close();
    }
  };

  es.onerror = () => {
    setStatus("Connection lost", "var(--error)");
    setBusy(false);
    es.close();
  };
}

// ── HELPERS ────────────────────────────────────────────────────────────────

function setStatus(text, color = "var(--dim)") {
  const el = document.getElementById("statusLabel");
  el.textContent = text;
  el.style.color = color;
}

function setOverall(v) {
  document.getElementById("overallFill").style.width = (v * 100).toFixed(1) + "%";
}

function setBusy(busy) {
  document.getElementById("fetchBtn").disabled = busy;
  document.getElementById("estimateBtn").disabled = busy || !videos.length;
  document.getElementById("dlBtn").disabled = busy || !videos.length;
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("urlInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") onFetch();
  });
});
