def format_size(b):
    if not b:
        return "—"
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} GB"


def format_dur(sec):
    if not sec:
        return "—"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def get_video_url(entry: dict) -> str | None:
    if entry.get('webpage_url'):
        return entry['webpage_url']
    vid_id = entry.get('id', '')
    if vid_id and len(vid_id) == 11:
        return f"https://www.youtube.com/watch?v={vid_id}"
    return None
