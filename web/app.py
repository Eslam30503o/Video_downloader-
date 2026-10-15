import os
import json
import queue
import threading
import uuid

import yt_dlp
from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from config import QUALITIES
from utils import format_dur, format_size, get_video_url

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# store active SSE queues per job_id
_job_queues: dict[str, queue.Queue] = {}

# in-memory session store: session_id -> list of entries
_sessions: dict[str, list] = {}


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", qualities=list(QUALITIES.keys()))


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify(error="No URL provided"), 400

    try:
        opts = {"quiet": True, "extract_flat": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entries = info.get("entries") or [info]
        entries = [e for e in entries if e]

        clean = []
        for e in entries:
            vurl = get_video_url(e)
            if vurl:
                clean.append({
                    "id":       e.get("id", ""),
                    "title":    e.get("title", "Unknown"),
                    "duration": format_dur(e.get("duration")),
                    "url":      vurl,
                    "thumb":    e.get("thumbnail", ""),
                })

        session_id = str(uuid.uuid4())
        _sessions[session_id] = clean

        return jsonify(session_id=session_id, videos=clean)

    except Exception as ex:
        return jsonify(error=str(ex)), 500


@app.route("/api/estimate", methods=["POST"])
def api_estimate():
    data = request.json
    session_id = data.get("session_id")
    indices = data.get("indices", [])
    quality = data.get("quality", "720p HD")

    entries = _sessions.get(session_id, [])
    if not entries:
        return jsonify(error="Session not found"), 404

    fmt = QUALITIES.get(quality, QUALITIES["720p HD"])
    results = {}
    total = 0

    opts = {"quiet": True, "no_warnings": True, "format": fmt, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        for i in indices:
            if i >= len(entries):
                continue
            vurl = entries[i]["url"]
            try:
                info = ydl.extract_info(vurl, download=False)
                size = info.get("filesize") or info.get("filesize_approx") or 0
                if not size:
                    for f in info.get("requested_formats", []):
                        size += f.get("filesize") or f.get("filesize_approx") or 0
                total += size
                results[i] = format_size(size) if size else "—"
            except Exception:
                results[i] = "—"

    return jsonify(sizes=results, total=format_size(total))


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.json
    session_id = data.get("session_id")
    indices = data.get("indices", [])
    quality = data.get("quality", "720p HD")

    entries = _sessions.get(session_id, [])
    if not entries:
        return jsonify(error="Session not found"), 404

    job_id = str(uuid.uuid4())
    q: queue.Queue = queue.Queue()
    _job_queues[job_id] = q

    fmt = QUALITIES.get(quality, QUALITIES["720p HD"])
    audio_only = "MP3" in quality

    threading.Thread(
        target=_download_worker,
        args=(job_id, entries, indices, fmt, audio_only),
        daemon=True,
    ).start()

    return jsonify(job_id=job_id)


@app.route("/api/progress/<job_id>")
def api_progress(job_id):
    """Server-Sent Events stream for download progress."""
    q = _job_queues.get(job_id)
    if not q:
        return jsonify(error="Job not found"), 404

    def stream():
        while True:
            try:
                msg = q.get(timeout=60)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") == "done":
                    break
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"
        _job_queues.pop(job_id, None)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/downloads/<path:filename>")
def serve_download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


# ── DOWNLOAD WORKER ───────────────────────────────────────────────────────────

def _download_worker(job_id, entries, indices, fmt, audio_only):
    q = _job_queues.get(job_id)
    if not q:
        return

    total = len(indices)
    pp = []
    if audio_only:
        pp.append({"key": "FFmpegExtractAudio",
                   "preferredcodec": "mp3", "preferredquality": "192"})

    for done, i in enumerate(indices):
        if i >= len(entries):
            continue
        entry = entries[i]
        vurl = entry["url"]

        q.put({"type": "start", "index": i, "title": entry["title"]})

        downloaded_file = {}

        def make_hook(idx):
            def hook(d):
                if d["status"] == "downloading":
                    try:
                        pct = float(d.get("_percent_str", "0%").strip().rstrip("%")) / 100
                    except ValueError:
                        pct = 0
                    spd = d.get("_speed_str", "").strip()
                    q.put({"type": "progress", "index": idx, "pct": pct, "speed": spd})
                elif d["status"] == "finished":
                    downloaded_file["path"] = d.get("filename", "")
            return hook

        opts = {
            "format": fmt,
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "postprocessors": pp,
            "merge_output_format": "mp4" if not audio_only else None,
            "ignoreerrors": True,
            "progress_hooks": [make_hook(i)],
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([vurl])
            # get final filename
            fname = os.path.basename(downloaded_file.get("path", ""))
            q.put({"type": "done_one", "index": i,
                   "file": fname, "overall": (done + 1) / total})
        except Exception as ex:
            q.put({"type": "error", "index": i, "msg": str(ex)})

    q.put({"type": "done", "overall": 1.0})


if __name__ == "__main__":
    app.run(debug=True, threaded=True)
