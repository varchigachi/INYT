from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import uuid
import shutil

# -----------------------------
# APP CONFIG
# -----------------------------
app = Flask(__name__)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# -----------------------------
# HELPERS
# -----------------------------
def ffmpeg_installed():
    """Check if ffmpeg is available in system."""
    return shutil.which("ffmpeg") is not None


def detect_platform(url: str):
    """Simple pattern detection for platform."""
    if "instagram.com" in url:
        return "instagram"
    if "shorts" in url:
        return "youtube_shorts"
    if "youtu" in url:
        return "youtube_video"
    return "unknown"


# -----------------------------
# ROUTES
# -----------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/metadata", methods=["POST"])
def metadata():
    """Fetch video metadata before download."""
    url = request.form.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    ydl_opts = {"quiet": True, "skip_download": True}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = []
            for f in info.get("formats", []):
                if f.get("filesize") and f.get("ext") in ["mp4", "m4a", "webm"]:
                    formats.append({
                        "id": f["format_id"],
                        "ext": f["ext"],
                        "res": f.get("height", "audio"),
                        "abr": f.get("abr"),
                        "filesize": round((f["filesize"] or 0) / 1_000_000, 1)
                    })

            return jsonify({
                "id": info.get("id"),
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration_string", ""),
                "formats": formats[:10],
                "platform": detect_platform(url)
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download", methods=["POST"])
def download():
    """Download handler for video/audio."""
    url = request.form.get("url")
    fmt_id = request.form.get("format_id")
    mode = request.form.get("mode", "video")

    if not url:
        return "Missing URL", 400

    file_id = str(uuid.uuid4())[:8]
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}_%(title)s.%(ext)s")

    # Base yt_dlp options
    ydl_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": r"C:\ffmpeg-8.0-essentials_build\bin",  # ⚙️ UPDATE TO YOUR FFmpeg PATH
    }

    # 🎧 Audio download
    if mode == "audio":
        ydl_opts.update({
            "format": "bestaudio[ext=m4a]/bestaudio/best",  # use m4a first
            "outtmpl": output_template,
            "quiet": False,  # show progress for debugging
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "postprocessor_args": ["-ar", "44100"],  # standard sample rate
            "ffmpeg_location": r"C:\ffmpeg-8.0-essentials_build\bin",     # ⚙️ set to your real path
            "ignoreerrors": True,
            "no_warnings": True,
            "cachedir": False,
        })

    else:
        # 🎥 Full video
        if ffmpeg_installed():
            ydl_opts["format"] = fmt_id or "bestvideo+bestaudio/best"
        else:
            ydl_opts["format"] = "best[ext=mp4]"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

            # Adjust filename for MP3 conversion
            if mode == "audio":
                base, _ = os.path.splitext(file_path)
                mp3_path = base + ".mp3"
                if os.path.exists(mp3_path):
                    file_path = mp3_path

        return send_file(file_path, as_attachment=True)

    except Exception as e:
        print("Download error:", e)
        return f"❌ Error: {str(e)}", 500


# -----------------------------
# START APP
# -----------------------------
if __name__ == "__main__":
    os.environ["FLASK_SKIP_DOTENV"] = "1"
    app.run(debug=True, use_reloader=False)
