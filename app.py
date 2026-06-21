import os, re, time, glob, threading, subprocess
from flask import Flask, request, send_file, abort

app = Flask(__name__)
CACHE_DIR = "/cache"
TTL = 1800          # 30 min: las URLs de vídeo de TikTok caducan
USER_TTL = 600      # 10 min: listados de perfil (yt-dlp es lento, cacheamos)
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
    for f in glob.glob(os.path.join(CACHE_DIR, "user_*.json")):
        try:
            if now - os.path.getmtime(f) > USER_TTL:
                os.remove(f)
        except OSError:
            pass
    for f in glob.glob(os.path.join(CACHE_DIR, "audio_*.m4a")):
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
            app.logger.warning("yt-dlp fallo vid=%s rc=%s err=%s", vid, r.returncode, r.stderr[-400:])
            return None
    return path

def _audio(vid, user):
    out = os.path.join(CACHE_DIR, f"audio_{vid}.m4a")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    with _lock(out):
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return out
        # Reutiliza el mp4 H.264 de /video (cacheado o nuevo) → su audio es AAC limpio.
        # Esquiva el bytevc1/HEVC que hace fallar a ffprobe con -x.
        mp4 = _download(vid, user, watermark=False)
        if not mp4:
            return None
        cmd = ["ffmpeg", "-y", "-i", mp4, "-vn", "-c:a", "copy", "-movflags", "+faststart", out]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0 or not (os.path.exists(out) and os.path.getsize(out) > 0):
            app.logger.warning("ffmpeg audio fallo vid=%s rc=%s err=%s", vid, r.returncode, r.stderr[-400:])
            return None
    return out

def _user_list(username, start, count):
    end = start + count - 1
    key = os.path.join(CACHE_DIR, f"user_{username}_{start}_{count}.json")
    if os.path.exists(key) and time.time() - os.path.getmtime(key) < USER_TTL:
        try:
            with open(key) as f:
                return f.read()
        except OSError:
            pass
    url = f"https://www.tiktok.com/@{username}"
    cmd = [
        "yt-dlp", "--flat-playlist", "--no-warnings", "-J",
        "--playlist-start", str(start), "--playlist-end", str(end),
        url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0 or not r.stdout:
        app.logger.warning("yt-dlp user fallo user=%s rc=%s err=%s", username, r.returncode, r.stderr[-400:])
        return None
    try:
        with open(key, "w") as f:
            f.write(r.stdout)
    except OSError:
        pass
    return r.stdout

_VID = re.compile(r"^\d{6,25}$")
_UNAME = re.compile(r"^[\w.]{1,24}$")

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

@app.route("/audio")
def audio():
    vid = request.args.get("id", "")
    user = request.args.get("user", "")
    if not _VID.match(vid):
        abort(400)
    _cleanup()
    path = _audio(vid, user)
    if not path:
        abort(502)
    return send_file(
        path, mimetype="audio/mp4", conditional=True,
        download_name=f"tiktok-{vid}.m4a",
    )

@app.route("/user")
def user():
    username = request.args.get("user", "")
    if not _UNAME.match(username):
        abort(400)
    try:
        start = max(1, int(request.args.get("start", 1)))
        count = min(50, max(1, int(request.args.get("count", 30))))
    except ValueError:
        abort(400)
    _cleanup()
    out = _user_list(username, start, count)
    if out is None:
        abort(502)
    return app.response_class(out, mimetype="application/json")