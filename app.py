import os, re, time, glob, threading, subprocess
from flask import Flask, request, send_file, abort

app = Flask(__name__)
CACHE_DIR = "/cache"
TTL = 1800  # 30 min: las URLs de TikTok caducan; no merece la pena guardar más
os.makedirs(CACHE_DIR, exist_ok=True)

_locks = {}
_master = threading.Lock()

def _lock(key):
    with _master:
        return _locks.setdefault(key, threading.Lock())

def _cleanup():
    now = time.time()
    for f in glob.glob(os.path.join(CACHE_DIR, "*.mp4")):
        try:
            if now - os.path.getmtime(f) > TTL:
                os.remove(f)
        except OSError:
            pass

def _download(vid, user, watermark):
    kind = "wm" if watermark else "nw"
    path = os.path.join(CACHE_DIR, f"{kind}_{vid}.mp4")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    with _lock(path):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        url = f"https://www.tiktok.com/@{user or '_'}/video/{vid}"
        # Forzar H.264 (los navegadores no reproducen el bytevc1/H.265 de TikTok) y remux a mp4.
        fmt = "download/b" if watermark else "b"
        cmd = [
            "yt-dlp", "--no-warnings", "--no-playlist",
            "-S", "vcodec:h264,res,br",
            "-f", fmt,
            "--remux-video", "mp4",
            "-o", path,
            url,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=100)
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0 or not (os.path.exists(path) and os.path.getsize(path) > 0):
            # log a stderr para depurar con `docker logs ttdlp_app`
            app.logger.warning("yt-dlp fallo vid=%s rc=%s err=%s", vid, r.returncode, r.stderr[-400:])
            return None
    return path

_VID = re.compile(r"^\d{6,25}$")

def _serve(watermark, attachment):
    vid = request.args.get("id", "")
    user = request.args.get("user", "")
    if not _VID.match(vid):
        abort(400)
    _cleanup()
    path = _download(vid, user, watermark)
    if not path:
        abort(502)
    suffix = "watermark" if watermark else "no_watermark"
    return send_file(
        path, mimetype="video/mp4", conditional=True,
        as_attachment=attachment, download_name=f"tiktok-{vid}-{suffix}.mp4",
    )

@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/video")
def video():
    return _serve(watermark=False, attachment=False)

@app.route("/download")
def download():
    wm = request.args.get("watermark") is not None
    return _serve(watermark=wm, attachment=True)