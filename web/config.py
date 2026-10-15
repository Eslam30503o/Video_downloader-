QUALITIES = {
    "Best Quality (4K/2K)": "bestvideo[vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "1080p HD":              "bestvideo[height<=1080][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p HD":               "bestvideo[height<=720][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":                  "bestvideo[height<=480][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p":                  "bestvideo[height<=360][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]",
    "Audio Only MP3":        "bestaudio/best",
}
