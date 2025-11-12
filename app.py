from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import uuid
import imageio_ffmpeg
import py_mini_racer  # Enables YouTube JS decryption

app = Flask(__name__)

# --- CONFIG ---
ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- Write cookies if provided from Render environment ---
cookies_env = os.environ.get("YOUTUBE_COOKIES")
if cookies_env:
    with open("cookies.txt", "w", encoding="utf-8") as f:
        f.write(cookies_env)


# ---------- HOME ----------
@app.route("/")
def index():
    return render_template("index.html")


# ---------- UNIVERSAL METADATA ----------
@app.route("/metadata", methods=["POST"])
def metadata():
    url = request.form.get("url")
    platform = request.form.get("platform", "youtube")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # Set default extractor options
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
            return jsonify({
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration_string", ""),
                "uploader": info.get("uploader", ""),
            })
    except Exception as e:
        print("Metadata error:", e)
        return jsonify({"error": f"⚠️ Could not fetch info: {str(e)}"}), 500


# ---------- UNIVERSAL DOWNLOAD ----------
@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url")
    platform = request.form.get("platform", "youtube")
    mode = request.form.get("mode", "video")

    if not url:
        return "Missing URL", 400

    file_id = str(uuid.uuid4())[:8]
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}_%(title)s.%(ext)s")
    progress_file = os.path.join(DOWNLOAD_DIR, f"{file_id}_progress.json")

    def progress_hook(d):
        try:
            if d["status"] == "downloading":
                percent = d.get("_percent_str", "0%").strip()
                with open(progress_file, "w") as f:
                    f.write(percent)
            elif d["status"] == "finished":
                with open(progress_file, "w") as f:
                    f.write("100%")
        except Exception:
            pass

    ydl_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_path,
        "progress_hooks": [progress_hook],
        "extractor_args": {"youtube": ["player_client=android"]},
        "no_warnings": True,
    }

    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

    if mode == "audio" and platform == "youtube":
        ydl_opts.update({
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        ydl_opts["format"] = "bestvideo+bestaudio/best"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            ydl.process_info(info)
            file_path = ydl.prepare_filename(info)

        if mode == "audio" and platform == "youtube":
            base, _ = os.path.splitext(file_path)
            mp3_path = base + ".mp3"
            if os.path.exists(mp3_path):
                file_path = mp3_path

        if os.path.exists(progress_file):
            os.remove(progress_file)

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


# ---------- PROGRESS ----------
@app.route("/progress/<file_id>")
def progress(file_id):
    progress_file = os.path.join(DOWNLOAD_DIR, f"{file_id}_progress.json")
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            return f.read()
    return "0%"


# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
