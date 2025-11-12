from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import uuid
import shutil
import imageio_ffmpeg
import py_mini_racer  # JS runtime for yt-dlp

app = Flask(__name__)

# ----- CONFIG -----
ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Write YouTube cookies from Render env variable if present
cookies_env = os.environ.get("YOUTUBE_COOKIES")
if cookies_env:
    with open("cookies.txt", "w", encoding="utf-8") as f:
        f.write(cookies_env)


# ---------- ROUTES ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/metadata", methods=["POST"])
def metadata():
    url = request.form.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extractor_args": {"youtube": ["player_client=android"]},
        "no_warnings": True,
        "ffmpeg_location": ffmpeg_path,
    }

    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

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
                "formats": formats[:10]
            })
    except Exception as e:
        return jsonify({"error": f"⚠️ Could not fetch metadata: {str(e)}"}), 500


@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url")
    fmt_id = request.form.get("format_id")
    mode = request.form.get("mode", "video")

    if not url:
        return "Missing URL", 400

    file_id = str(uuid.uuid4())[:8]
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}_%(title)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_path,
        "extractor_args": {"youtube": ["player_client=android"]},
        "no_warnings": True
    }

    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

    if mode == "audio":
        ydl_opts.update({
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        ydl_opts["format"] = fmt_id or "bestvideo+bestaudio/best"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            ydl.process_info(info)
            file_path = ydl.prepare_filename(info)

            if mode == "audio":
                base, _ = os.path.splitext(file_path)
                mp3_path = base + ".mp3"
                if os.path.exists(mp3_path):
                    file_path = mp3_path

        print("✅ Sending file:", file_path)
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=os.path.basename(file_path),
            mimetype="application/octet-stream",
            max_age=0
        )

        @response.call_on_close
        def cleanup():
            try:
                os.remove(file_path)
            except:
                pass

        return response

    except Exception as e:
        print("Download error:", e)
        return f"❌ Error: {str(e)}", 500


# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
