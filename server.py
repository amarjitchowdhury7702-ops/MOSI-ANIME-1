#!/usr/bin/env python3
"""
MOSI ANIME server (Python standard library only, nothing to install)

  python3 server.py                 -> http://localhost:8080
  Admin panel                       -> http://localhost:8080/admin.html
  Admin key                         -> env MOSI_ADMIN_KEY (default "mosi-admin")
  YouTube Data API key (free)       -> paste it in the admin panel, or env YT_API_KEY

What it does
  * Serves the website
  * Finds FULL EPISODES on official free anime channels (Muse India, Muse Asia,
    Ani-One Asia) using the YouTube Data API, and plays them in the MOSI player
  * Stores requests, notify sign-ups, donation notes and donated videos (./data, ./uploads)
"""
import json, os, re, threading, time, uuid
import urllib.request, urllib.parse, urllib.error
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DATA_DIR") or os.path.join(ROOT, "data")          # point at a persistent disk when hosting
UPLOADS = os.environ.get("UPLOADS_DIR") or os.path.join(ROOT, "uploads")
PORT = int(os.environ.get("PORT", 8080))
ADMIN_KEY = os.environ.get("MOSI_ADMIN_KEY", "mosi-admin")
YT_API = os.environ.get("YT_API_BASE", "https://www.googleapis.com/youtube/v3")
REGION = os.environ.get("MOSI_REGION", "IN")            # skip videos blocked in this country
MAX_UPLOAD = 4 * 1024 ** 3
VIDEO_EXT = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi", ".ogg"}
INDEX_TTL = 24 * 3600          # refresh the channel playlist list once a day
ITEMS_TTL = 6 * 3600           # refresh a playlist's episodes every 6 hours

# Official, licensed channels that post full anime episodes for free
CHANNELS = [
    {"name": "Muse India",   "id": "UCYYhAzgWuxPauRXdPpLAX3Q"},
    {"name": "Muse Asia",    "id": "UCGbshtvS9t-8CW11W7TooQg"},
    {"name": "Ani-One Asia", "id": "UC0wNSTMWIL3qaorLx0jie6A"},
]

os.makedirs(DATA, exist_ok=True)
os.makedirs(UPLOADS, exist_ok=True)
LOCK = threading.Lock()
YT_LOCK = threading.Lock()


# ---------------------------------------------------------------- storage
def load(name, default):
    p = os.path.join(DATA, name + ".json")
    if not os.path.exists(p):
        return json.loads(json.dumps(default))
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(default))

def save(name, obj):
    p = os.path.join(DATA, name + ".json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)

def clip(v, n=300):
    return str(v or "")[:n]

def yt_key():
    return os.environ.get("YT_API_KEY") or load("config", {}).get("youtubeKey", "")


# ---------------------------------------------------------------- YouTube
class YTError(Exception):
    pass

def yt_get(endpoint, **params):
    key = yt_key()
    if not key:
        raise YTError("YouTube API key not set (add it in the admin panel)")
    params["key"] = key
    url = f"{YT_API}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "MOSI-ANIME/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e)["error"]["message"]
        except Exception:
            msg = str(e)
        if "quota" in msg.lower():
            msg = "YouTube daily quota used up. Try again tomorrow."
        raise YTError(re.sub("<[^>]+>", "", msg))
    except urllib.error.URLError as e:
        raise YTError(f"Can't reach YouTube: {e.reason}")

INDEX_STATE = {"building": False, "error": "", "updated": 0, "counts": {}}

def build_index(force=False):
    """Download the playlist list of every official channel (≈1 quota unit per 50 playlists)."""
    if not YT_LOCK.acquire(blocking=False):
        return
    try:
        idx = load("yt_index", {})
        if not force and idx and time.time() - min(v.get("at", 0) for v in idx.values()) < INDEX_TTL and len(idx) == len(CHANNELS):
            INDEX_STATE.update(updated=min(v["at"] for v in idx.values()), counts={k: len(v["playlists"]) for k, v in idx.items()}, error="")
            return
        INDEX_STATE.update(building=True, error="")
        new = {}
        for ch in CHANNELS:
            pls, token = [], None
            for _ in range(80):                                 # up to 4000 playlists per channel
                kw = dict(part="snippet,contentDetails", channelId=ch["id"], maxResults=50)
                if token:
                    kw["pageToken"] = token
                d = yt_get("playlists", **kw)
                for it in d.get("items", []):
                    n = it.get("contentDetails", {}).get("itemCount", 0)
                    if n:
                        sn = it["snippet"]
                        pls.append({"id": it["id"], "title": sn.get("title", ""), "count": n,
                                    "thumb": (sn.get("thumbnails", {}).get("medium") or {}).get("url", "")})
                token = d.get("nextPageToken")
                if not token:
                    break
            new[ch["name"]] = {"id": ch["id"], "at": time.time(), "playlists": pls}
        save("yt_index", new)
        save("yt_check", {})                                    # matches may change
        INDEX_STATE.update(updated=time.time(), counts={k: len(v["playlists"]) for k, v in new.items()})
    except YTError as e:
        INDEX_STATE["error"] = str(e)
    finally:
        INDEX_STATE["building"] = False
        YT_LOCK.release()

def ensure_index_async():
    if yt_key() and not INDEX_STATE["building"]:
        threading.Thread(target=build_index, daemon=True).start()

def norm(s):
    s = str(s or "").lower().replace("×", "x").replace("&", " and ")
    s = re.sub(r"[\[\(【「].*?[\]\)】」]", " ", s)               # drop [English Sub], (Hindi Dub) ...
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())

NOISE_RE = re.compile(r"\b(english|eng|sub|subs|subbed|subtitles?|dub|dubbed|hindi|tamil|telugu|bengali|indonesian|thai|"
                      r"vietnamese|chinese|malay|full|episodes?|eps|official|anime|series|tv|uncut|multi|audio|ver|version|all)\b")
SEASON = r"(?:season \d+|\d+(?:st|nd|rd|th) season|s\d+|part \d+|cour \d+|\d+|final season|the final season)"

def clean_title(t):
    return " ".join(NOISE_RE.sub(" ", norm(t)).split())

def match_playlists(titles):
    """Strict match: playlist must be exactly the anime title (+ optional season/part number and language tags)."""
    idx = load("yt_index", {})
    cands = sorted({norm(t) for t in titles if len(norm(t)) >= 2}, key=len, reverse=True)
    if not cands:
        return []
    pats = [(c, re.compile(re.escape(c) + rf"(?: {SEASON})*")) for c in cands]
    out = []
    for ch_name, ch in idx.items():
        for p in ch.get("playlists", []):
            pt = clean_title(p["title"])
            if not pt:
                continue
            score = 0
            for c, pat in pats:
                if pt == c or norm(p["title"]) == c:
                    score = 2; break
                if pat.fullmatch(pt):
                    score = max(score, 1)
            if score:
                tl = p["title"].lower()
                lang = "Hindi" if "hindi" in tl else ("Dub" if "dub" in tl else "Sub")
                out.append((score, {**p, "channel": ch_name, "lang": lang}))
    out.sort(key=lambda x: (-x[0], -x[1]["count"]))
    return [p for _, p in out[:15]]

EP_RE = re.compile(r"(?:episode|ep\.?|eps)\s*0*(\d{1,4})", re.I)

def playlist_episodes(pid):
    cache = load("yt_items", {})
    c = cache.get(pid)
    if c and time.time() - c["at"] < ITEMS_TTL:
        return c["episodes"]
    items, token = [], None
    for _ in range(40):                                         # up to 2000 episodes
        kw = dict(part="snippet", playlistId=pid, maxResults=50)
        if token:
            kw["pageToken"] = token
        d = yt_get("playlistItems", **kw)
        for it in d.get("items", []):
            sn = it["snippet"]
            vid = sn.get("resourceId", {}).get("videoId")
            if not vid or sn.get("title") in ("Private video", "Deleted video"):
                continue
            items.append({"videoId": vid, "title": sn.get("title", ""), "pos": sn.get("position", len(items)),
                          "thumb": (sn.get("thumbnails", {}).get("medium") or {}).get("url", "")})
        token = d.get("nextPageToken")
        if not token:
            break
    # keep only public, embeddable videos that aren't blocked in REGION
    ok = set()
    for i in range(0, len(items), 50):
        ids = ",".join(x["videoId"] for x in items[i:i + 50])
        d = yt_get("videos", part="status,contentDetails", id=ids)
        for v in d.get("items", []):
            st, rr = v.get("status", {}), v.get("contentDetails", {}).get("regionRestriction", {})
            if st.get("privacyStatus") != "public" or st.get("embeddable") is False:
                continue
            if REGION in rr.get("blocked", []) or ("allowed" in rr and REGION not in rr["allowed"]):
                continue
            ok.add(v["id"])
    eps = []
    for x in items:
        if x["videoId"] in ok:
            m = EP_RE.search(x["title"])
            eps.append({**x, "n": int(m.group(1)) if m else None})
    if eps and all(e["n"] is not None for e in eps):
        eps.sort(key=lambda e: (e["n"], e["pos"]))
    for i, e in enumerate(eps):
        if e["n"] is None:
            e["n"] = i + 1
    with LOCK:
        cache = load("yt_items", {})
        cache[pid] = {"at": time.time(), "episodes": eps}
        save("yt_items", cache)
    return eps


# ---------------------------------------------------------------- HTTP
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or ""):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 2_000_000:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def is_admin(self):
        return self.headers.get("X-Admin-Key") == ADMIN_KEY

    # ---------- GET ----------
    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        if path in ("/", "/index.html"):
            self.path = "/src.html"
            return super().do_GET()
        if path == "/api/library":
            return self.send_json(load("library", {}))
        if path == "/api/requests":
            return self.send_json(load("requests", {}))
        if path == "/api/status":
            return self.send_json({"stream": bool(yt_key()), "indexing": INDEX_STATE["building"],
                                   "ready": bool(load("yt_index", {})), "error": INDEX_STATE["error"]})
        if path == "/api/stream/episodes":
            pid = (q.get("pid") or [""])[0]
            if not re.fullmatch(r"[\w-]{10,64}", pid):
                return self.send_json({"error": "bad playlist id"}, 400)
            try:
                return self.send_json({"episodes": playlist_episodes(pid)})
            except YTError as e:
                return self.send_json({"error": str(e)}, 502)
        if path == "/api/admin/all":
            if not self.is_admin():
                return self.send_json({"error": "wrong admin key"}, 401)
            out = {k: load(k, d) for k, d in [("library", {}), ("requests", {}), ("contributions", []), ("donations", []), ("notify", [])]}
            key = yt_key()
            out["youtube"] = {"hasKey": bool(key), "keyHint": (key[:4] + "…" + key[-4:]) if key else "",
                              "fromEnv": bool(os.environ.get("YT_API_KEY")), **INDEX_STATE,
                              "channels": [c["name"] for c in CHANNELS]}
            return self.send_json(out)
        if path.startswith("/data/") or path.endswith((".py", ".yaml", ".md")) or path.startswith("/.") or path in ("/Dockerfile", "/Procfile"):
            return self.send_error(404)
        if path.startswith("/uploads/"):
            return self.serve_range(path)
        return super().do_GET()

    def serve_range(self, path):
        name = os.path.basename(urllib.parse.unquote(path))
        fp = os.path.join(UPLOADS, name)
        if not os.path.isfile(fp):
            return self.send_error(404)
        size = os.path.getsize(fp)
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if m:
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            elif m.group(2):
                start = max(0, size - int(m.group(2)))
            if start > end:
                self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", self.guess_type(fp))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(fp, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    # ---------- POST ----------
    def do_POST(self):
        u = urlparse(self.path)
        p, q = u.path, parse_qs(u.query)
        try:
            if p == "/api/upload":
                return self.handle_upload(q)
            body = self.read_json()

            if p == "/api/stream/check":
                # which of these anime have free official episodes? (uses the cached index: 0 quota)
                if not yt_key():
                    return self.send_json({"enabled": False, "available": {}})
                if not load("yt_index", {}):
                    ensure_index_async()
                    return self.send_json({"enabled": True, "ready": False, "available": {}})
                cache = load("yt_check", {})
                res, changed = {}, False
                for it in body.get("items", [])[:120]:
                    aid = clip(it.get("id"), 20)
                    if aid not in cache:
                        cache[aid] = bool(match_playlists([clip(t, 200) for t in it.get("titles", [])][:12]))
                        changed = True
                    res[aid] = cache[aid]
                if changed:
                    with LOCK:
                        save("yt_check", {**load("yt_check", {}), **cache})
                return self.send_json({"enabled": True, "ready": True, "available": res})

            if p == "/api/stream/find":
                if not yt_key():
                    return self.send_json({"enabled": False, "sources": []})
                if not load("yt_index", {}):
                    build_index()
                    if not load("yt_index", {}):
                        return self.send_json({"enabled": True, "sources": [], "error": INDEX_STATE["error"] or "index not ready"})
                srcs = match_playlists([clip(t, 200) for t in body.get("titles", [])][:12])
                return self.send_json({"enabled": True, "sources": [
                    {k: s[k] for k in ("id", "title", "count", "channel", "lang", "thumb")} for s in srcs]})

            with LOCK:
                if p == "/api/request":
                    reqs = load("requests", {})
                    aid = clip(body.get("id"), 20)
                    r = reqs.get(aid, {"count": 0, "title": clip(body.get("title")), "img": clip(body.get("img"), 500)})
                    r["count"] += 1
                    reqs[aid] = r
                    save("requests", reqs)
                    return self.send_json({"count": r["count"]})
                if p == "/api/notify":
                    n = load("notify", [])
                    n.append({"id": clip(body.get("id"), 20), "title": clip(body.get("title")), "email": clip(body.get("email"), 120), "at": time.time()})
                    save("notify", n)
                    return self.send_json({"ok": True})
                if p == "/api/donation":
                    d = load("donations", [])
                    d.append({"name": clip(body.get("name"), 80), "amount": body.get("amount"), "anime": clip(body.get("anime")),
                              "animeId": body.get("animeId"), "at": time.time()})
                    save("donations", d)
                    return self.send_json({"ok": True})
                if p == "/api/contribute":
                    c = load("contributions", [])
                    cid = uuid.uuid4().hex[:10]
                    c.append({"id": cid, "status": "pending", "at": time.time(), "file": "",
                              **{k: clip(body.get(k), 500) for k in ("anime", "img", "episodes", "lang", "quality", "link", "name", "email", "fileName")},
                              "animeId": body.get("animeId")})
                    save("contributions", c)
                    return self.send_json({"id": cid})
                if p.startswith("/api/admin/"):
                    if not self.is_admin():
                        return self.send_json({"error": "wrong admin key"}, 401)
                    return self.handle_admin(p, body)
            return self.send_json({"error": "not found"}, 404)
        except Exception as e:
            return self.send_json({"error": str(e)}, 400)

    def handle_upload(self, q):
        cid = (q.get("cid") or [""])[0]
        name = (q.get("name") or ["video.mp4"])[0]
        ext = os.path.splitext(name)[1].lower()
        if ext not in VIDEO_EXT:
            return self.send_json({"error": "only video files are allowed"}, 400)
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_UPLOAD:
            return self.send_json({"error": "file too large or empty"}, 400)
        with LOCK:
            item = next((x for x in load("contributions", []) if x["id"] == cid), None)
        if not item:
            return self.send_json({"error": "unknown submission"}, 400)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.splitext(name)[0])[:60]
        fname = f"{cid}-{safe}{ext}"
        left = n
        with open(os.path.join(UPLOADS, fname), "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        with LOCK:
            c = load("contributions", [])
            for x in c:
                if x["id"] == cid:
                    x["file"] = "/uploads/" + fname
            save("contributions", c)
        return self.send_json({"ok": True, "file": "/uploads/" + fname})

    def handle_admin(self, p, body):
        lib = load("library", {})
        if p == "/api/admin/config":
            cfg = load("config", {})
            cfg["youtubeKey"] = clip(body.get("youtubeKey"), 100).strip()
            save("config", cfg)
            save("yt_check", {})
            if cfg["youtubeKey"]:
                threading.Thread(target=build_index, kwargs={"force": True}, daemon=True).start()
            return self.send_json({"ok": True})
        if p == "/api/admin/reindex":
            if not yt_key():
                return self.send_json({"error": "add a YouTube API key first"}, 400)
            threading.Thread(target=build_index, kwargs={"force": True}, daemon=True).start()
            return self.send_json({"ok": True})
        if p == "/api/admin/approve":
            c = load("contributions", [])
            item = next((x for x in c if x["id"] == body.get("cid")), None)
            if not item:
                return self.send_json({"error": "submission not found"}, 404)
            aid = str(body.get("animeId") or item.get("animeId") or "").strip()
            if not aid:
                return self.send_json({"error": "AniList ID required"}, 400)
            src = item.get("file") or item.get("link")
            if not src:
                return self.send_json({"error": "submission has no video"}, 400)
            entry = lib.get(aid, {"title": item.get("anime"), "img": item.get("img"), "episodes": []})
            entry.setdefault("episodes", []).append({"ep": item.get("episodes") or "1", "lang": item.get("lang"),
                                                     "quality": item.get("quality"), "src": src, "by": item.get("name")})
            if not entry.get("img") and item.get("img"):
                entry["img"] = item["img"]
            lib[aid] = entry
            item["status"], item["animeId"] = "approved", aid
            save("library", lib); save("contributions", c)
            return self.send_json({"ok": True})
        if p == "/api/admin/reject":
            c = load("contributions", [])
            for x in c:
                if x["id"] == body.get("cid"):
                    x["status"] = "rejected"
            save("contributions", c)
            return self.send_json({"ok": True})
        if p == "/api/admin/remove":
            lib.pop(str(body.get("animeId")), None)
            save("library", lib)
            return self.send_json({"ok": True})
        if p == "/api/admin/add":
            aid = str(body.get("animeId") or "").strip()
            if not aid or not body.get("src"):
                return self.send_json({"error": "AniList ID and video link required"}, 400)
            entry = lib.get(aid, {"title": clip(body.get("title")) or "Anime " + aid, "img": clip(body.get("img"), 500), "episodes": []})
            entry.setdefault("episodes", []).append({"ep": clip(body.get("ep"), 20) or "1", "lang": clip(body.get("lang"), 40), "src": clip(body.get("src"), 500)})
            lib[aid] = entry
            save("library", lib)
            return self.send_json({"ok": True})
        return self.send_json({"error": "unknown admin action"}, 404)


if __name__ == "__main__":
    if ADMIN_KEY == "mosi-admin":
        print("⚠️  WARNING: using the default admin key. Set MOSI_ADMIN_KEY before going public!")
    if yt_key():
        ensure_index_async()
    print(f"MOSI ANIME running on http://0.0.0.0:{PORT}   admin key: {ADMIN_KEY}   "
          f"auto-play: {'ON' if yt_key() else 'OFF (add a YouTube API key in admin.html)'}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
