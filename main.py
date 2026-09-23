import asyncio
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import base64
import random
import edge_tts
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

WORK = Path("/tmp/novavids")
WORK.mkdir(exist_ok=True)
UPLOADS = WORK / "uploads"
UPLOADS.mkdir(exist_ok=True)


# ============================================================
# Persistencia: Supabase Storage (opcional, via SUPA_URL + SUPA_KEY)
# ============================================================

SUPA_URL = os.environ.get("SUPA_URL", "").rstrip("/")
SUPA_KEY = os.environ.get("SUPA_KEY", "")
SUPA_LIMIT = 800 * 1024 * 1024


def _supa_req(method: str, path: str, data=None, ctype="application/octet-stream"):
    if not SUPA_URL or not SUPA_KEY:
        raise RuntimeError("supabase not configured")
    url = SUPA_URL + "/storage/v1/" + path
    hdr = {"Authorization": "Bearer " + SUPA_KEY, "apikey": SUPA_KEY}
    if isinstance(data, (bytes, bytearray)):
        hdr["Content-Type"] = ctype
    elif data is not None:
        hdr["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    if method in ("POST", "PUT"):
        hdr["x-upsert"] = "true"
    r = urllib.request.Request(url, data=data, headers=hdr, method=method)
    return urllib.request.urlopen(r, timeout=30)


def _supa_public(vid: str) -> str:
    return f"{SUPA_URL}/storage/v1/object/public/videos/{vid}.mp4"


def _rpc(fn: str, params: dict = None):
    url = SUPA_URL + "/rest/v1/rpc/" + fn
    hdr = {"Authorization": "Bearer " + SUPA_KEY, "apikey": SUPA_KEY,
           "Content-Type": "application/json"}
    data = json.dumps(params or {}).encode()
    r = urllib.request.Request(url, data=data, headers=hdr, method="POST")
    return json.loads(urllib.request.urlopen(r, timeout=30).read())


def _db_list(lim: int = 50) -> list:
    try:
        return _rpc("videos_list", {"lim": lim})
    except Exception as e:
        print("videos_list failed:", e, flush=True)
        return []


def _manifest() -> list:
    try:
        with _supa_req("GET", "object/public/videos/manifest.json") as r:
            return json.loads(r.read())
    except Exception:
        return []


def _db_migrate():
    try:
        have = {i["video_id"] for i in _db_list(500)}
        for i in _manifest():
            if i.get("video_id") and i["video_id"] not in have:
                _rpc("videos_insert", {"p_id": i["video_id"],
                                       "p_char": i.get("char", "")[:140],
                                       "p_scene": i.get("scene", "")[:140],
                                       "p_size": i.get("size", 0)})
    except Exception as e:
        print("migrate failed:", e, flush=True)


def _store_video(vid: str, char_prompt: str, scene_prompt: str, mp4: Path):
    if not SUPA_URL or not SUPA_KEY:
        return
    try:
        _supa_req("PUT", f"object/videos/{vid}.mp4", mp4.read_bytes(), "video/mp4")
        _rpc("videos_insert", {"p_id": vid, "p_char": char_prompt[:140],
                               "p_scene": scene_prompt[:140],
                               "p_size": mp4.stat().st_size})
        items = _db_list(500)
        total = sum(i.get("size", 0) for i in items)
        for old in items[::-1]:
            if total <= SUPA_LIMIT:
                break
            try:
                _supa_req("DELETE", f"object/videos/{old['video_id']}.mp4")
                _rpc("videos_delete", {"p_id": old["video_id"]})
            except Exception:
                pass
            total -= old.get("size", 0)
    except Exception as e:
        print("store_video failed:", e, flush=True)


def _supa_has(vid: str) -> bool:
    if not SUPA_URL or not SUPA_KEY:
        return False
    try:
        r = urllib.request.Request(_supa_public(vid), method="HEAD")
        return urllib.request.urlopen(r, timeout=15).status == 200
    except Exception:
        return False


# ============================================================
# Platform: Pollinations.ai — imagen de personaje y escena
# ============================================================

POLL = "https://image.pollinations.ai/prompt/{p}?width=720&height=1280&nologo=true&seed={s}"
POLL_TOKEN = os.environ.get("POLL_TOKEN", "")


def _poll_url(prompt: str, seed: int, token: bool = True) -> str:
    u = POLL.format(p=prompt, s=seed)
    return u + ("&token=" + POLL_TOKEN if token and POLL_TOKEN else "")


def _dl_poll(prompt: str, seed: int, out: Path):
    try:
        _dl(_poll_url(prompt, seed), out)
    except Exception:
        _dl(_poll_url(prompt, seed, token=False), out)


def _char_image_prompt(description: str) -> str:
    return urllib.parse.quote(
        "photorealistic portrait, sharp detailed face, symmetrical face, "
        "beautiful eyes, high quality, " + description
        + ", natural skin texture, soft light, clean background")


VIEW_PROMPTS = {
    "front": "full body front view, standing straight, facing camera",
    "profile": "full body side profile view, standing straight",
    "back": "full body back view, standing straight, facing away from camera",
    "face": "extreme close-up face portrait, sharp focus on eyes, detailed skin",
}


def _char_view_prompt(description: str, view: str) -> str:
    base = VIEW_PROMPTS.get(view, VIEW_PROMPTS["front"])
    style = ("detailed realistic face, symmetrical, beautiful eyes, "
             if view == "face" else
             "detailed realistic face, symmetrical, beautiful eyes, "
             "full body visible head to toe, ")
    return urllib.parse.quote(
        "photorealistic, " + base + ", " + style + description
        + ", natural skin texture, soft light, neutral background, high quality")


def _scene_image_prompt(char_prompt: str, scene_prompt: str) -> str:
    return urllib.parse.quote(
        "photorealistic candid phone photo, " + char_prompt + ", "
        + scene_prompt + ", natural skin, imperfect, indoor light")


def _dl(url: str, out: Path, retries: int = 6):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as f:
                f.write(r.read())
            return
        except Exception as e:
            last = e
            time.sleep(min(10 * (i + 1), 30))
    raise last


# ============================================================
# Platform: Microsoft Edge TTS — voz (es-CL)
# ============================================================

VOICES = {"female": "es-CL-CatalinaNeural", "male": "es-CL-LorenzoNeural"}


async def _tts(text: str, mp3: Path, srt: Path, voice: str):
    c = edge_tts.Communicate(text, VOICES.get(voice, VOICES["female"]),
                             rate="+5%", boundary="SentenceBoundary")
    subm = edge_tts.SubMaker()
    with open(mp3, "wb") as f:
        async for chunk in c.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                subm.feed(chunk)
    srt.write_text(subm.get_srt())


# ============================================================
# Platform: HuggingFace Space (Wan 2.2 Lightning, ZeroGPU)
# — video real img2video — wan_gen.py
# ============================================================


def _animate_wan(img: Path, scene_prompt: str, out: Path, seed: int,
                 uncensored: bool = False):
    import wan_gen
    motion = ("natural body motion, subtle movement, "
              + scene_prompt + ", cinematic")
    wan_gen.generate(str(img), motion, str(out), seed,
                     safe_mode=not uncensored)


# ============================================================
# Platform: Vidu — video img2video de respaldo (solo VM) — vidu_gen.py
# ============================================================


def _animate_vidu(img: Path, scene_prompt: str, out: Path):
    import vidu_gen
    vidu_gen.generate_sync(img, scene_prompt, out)


# ============================================================
# Platform: fal.ai — Wan 2.2 serverless, pago por uso (~$0.05/video)
# ============================================================

FAL_KEY = os.environ.get("FAL_KEY", "").strip()
FAL_MODEL = "fal-ai/wan-i2v"


def _animate_fal(img: Path, scene_prompt: str, out: Path, seconds: float):
    if not FAL_KEY:
        raise RuntimeError("fal: sin FAL_KEY")
    hdrs = {"Authorization": "Key " + FAL_KEY,
            "Content-Type": "application/json"}
    body = {
        "prompt": ("natural body motion, subtle movement, "
                   + scene_prompt + ", cinematic"),
        "image_url": "data:image/jpeg;base64,"
                     + base64.b64encode(img.read_bytes()).decode(),
        "video_length": "5 Seconds" if seconds <= 6 else "10 Seconds",
        "resolution": "480p",
    }
    req = urllib.request.Request(
        "https://queue.fal.run/" + FAL_MODEL, data=json.dumps(body).encode(),
        headers=hdrs, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    status_url, resp_url = r.get("status_url"), r.get("response_url")
    if not status_url or not resp_url:
        raise RuntimeError("fal: " + json.dumps(r)[:200])
    deadline = time.time() + 780
    while time.time() < deadline:
        time.sleep(5)
        st = json.loads(urllib.request.urlopen(urllib.request.Request(
            status_url, headers=hdrs), timeout=30).read())
        if st.get("status") == "COMPLETED":
            res = json.loads(urllib.request.urlopen(urllib.request.Request(
                resp_url, headers=hdrs), timeout=60).read())
            vurl = (res.get("video") or {}).get("url")
            if not vurl:
                raise RuntimeError("fal: sin video en respuesta")
            out.write_bytes(urllib.request.urlopen(vurl, timeout=120).read())
            return
        if st.get("status") in ("FAILED", "ERROR"):
            raise RuntimeError("fal: " + json.dumps(st)[:200])
    raise RuntimeError("fal: timeout esperando video")


KAGGLE_URL = os.environ.get("KAGGLE_VIDEO_URL", "").rstrip("/")
KAGGLE_SECRET = os.environ.get("KAGGLE_SECRET", "")
_KAGGLE_FILE = Path("/tmp/kaggle_url.txt")
if not KAGGLE_URL and _KAGGLE_FILE.exists():
    KAGGLE_URL = _KAGGLE_FILE.read_text().strip()


def _kaggle_url_load():
    """Recupera la última URL registrada desde Supabase (sobrevive a reinicios
    de Render, a diferencia de /tmp que se borra en cada deploy/cold start)."""
    global KAGGLE_URL
    if KAGGLE_URL or not SUPA_URL or not SUPA_KEY:
        return
    try:
        with _supa_req("GET", "object/videos/_kaggle_url.txt") as r:
            url = r.read().decode().strip()
        if url:
            KAGGLE_URL = url
            _KAGGLE_FILE.write_text(url)
    except Exception as e:
        print("kaggle_url_load failed:", e, flush=True)


def _kaggle_url_save(url: str):
    _KAGGLE_FILE.write_text(url)
    if SUPA_URL and SUPA_KEY:
        try:
            _supa_req("PUT", "object/videos/_kaggle_url.txt", url.encode(),
                      "text/plain")
        except Exception as e:
            print("kaggle_url_save failed:", e, flush=True)


_kaggle_url_load()


@app.get("/api/kaggle/register")
async def kaggle_status():
    return {"ok": True, "url": KAGGLE_URL}


@app.post("/api/kaggle/register")
async def kaggle_register(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if KAGGLE_SECRET and body.get("secret") != KAGGLE_SECRET:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"ok": False, "error": {"code": 401, "message": "unauthorized"}},
            status_code=401)
    url = str(body.get("url", "")).rstrip("/")
    if not url.startswith("https://"):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"ok": False, "error": {"code": 400, "message": "url inválida"}},
            status_code=400)
    try:
        urllib.request.urlopen(url + "/health", timeout=20)
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"ok": False, "error": {"code": 400,
                                    "message": f"url no responde: {type(e).__name__}: {e}"}},
            status_code=400)
    global KAGGLE_URL
    KAGGLE_URL = url
    _kaggle_url_save(url)
    return {"ok": True}


def _animate_kaggle(img: Path, scene_prompt: str, out: Path, seconds: float):
    if not KAGGLE_URL:
        raise RuntimeError("kaggle not configured")
    payload = json.dumps({
        "image_b64": base64.b64encode(img.read_bytes()).decode(),
        "prompt": scene_prompt, "seconds": min(max(seconds, 2.0), 5.0)
    }).encode()
    req = urllib.request.Request(
        KAGGLE_URL + "/generate", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=120).read())
    if not r.get("ok"):
        raise RuntimeError("kaggle: " + str(r.get("error", "generate failed"))[:200])
    if r.get("video_b64"):  # respuesta directa
        out.write_bytes(base64.b64decode(r["video_b64"]))
        return
    job = r.get("job")
    if not job:
        raise RuntimeError("kaggle: sin job ni video")
    deadline = time.time() + 780  # 13 min
    while time.time() < deadline:
        time.sleep(10)
        try:
            rr = json.loads(urllib.request.urlopen(
                KAGGLE_URL + "/result?id=" + job, timeout=30).read())
        except Exception:
            continue
        if not rr.get("ok"):
            continue
        if rr.get("status") == "done":
            out.write_bytes(base64.b64decode(rr["video_b64"]))
            return
        if rr.get("status") == "error":
            raise RuntimeError("kaggle: " + str(rr.get("error", ""))[:200])
    raise RuntimeError("kaggle: timeout esperando video")


_MOTION_CACHE = {"ts": 0.0, "ok": False, "dead_until": 0.0}


def _motion_available() -> bool:
    now = time.time()
    if now < _MOTION_CACHE["dead_until"]:
        # Wan HF sin cuota por ahora — pero si Kaggle responde, igual hay animación
        if KAGGLE_URL:
            try:
                urllib.request.urlopen(KAGGLE_URL + "/health", timeout=8)
                return True
            except Exception:
                pass
        return False
    if KAGGLE_URL:
        try:
            urllib.request.urlopen(KAGGLE_URL + "/health", timeout=8)
            _MOTION_CACHE.update(ts=now, ok=True)
            return True
        except Exception:
            pass
    if now - _MOTION_CACHE["ts"] < 60:
        return _MOTION_CACHE["ok"]
    import wan_gen
    hdrs = {"User-Agent": "nova-studio"}
    token = os.environ.get("HF_TOKEN")
    if token:
        hdrs["Authorization"] = "Bearer " + token
    ok = False
    for path in ("/gradio_api/info", "/"):
        try:
            req = urllib.request.Request(wan_gen.BASE + path, headers=hdrs)
            with urllib.request.urlopen(req, timeout=8) as r:
                ok = r.status == 200
            break
        except Exception:
            continue
    _MOTION_CACHE.update(ts=now, ok=ok)
    return ok


def _motion_mark(ok: bool):
    if ok:
        _MOTION_CACHE.update(ts=time.time(), ok=True, dead_until=0.0)
    else:
        # real generation failed -> treat motion as down for 10 min
        _MOTION_CACHE.update(ts=time.time(), ok=False,
                             dead_until=time.time() + 600)


# ============================================================
# Platform: local — ffmpeg (fallback de video y mux de audio/subs)
# ============================================================

SUB_STYLE = ("FontName=DejaVu Sans,FontSize=14,Bold=1,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,Outline=2,Shadow=1,Alignment=2,MarginV=340")


def _sub_filter(srt: Path) -> str:
    sub = str(srt).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return ",subtitles='%s':force_style='%s'" % (sub, SUB_STYLE)


def _render(img: Path, audio: Path | None, srt: Path | None, out: Path, dur: float):
    frames = int(dur * 24)
    step = 0.15 / frames
    # render at output size directly — avoids the 2048x3072 intermediate that OOMs free tier
    vf = ("scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
          "zoompan=z='min(zoom+%.6f,1.15)':"
          "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=720x1280:fps=24" % (step, frames))
    if srt and srt.exists() and srt.read_text().strip():
        vf += _sub_filter(srt)
    if audio:
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(audio),
               "-filter_complex", vf, "-t", str(dur), "-c:v", "libx264",
               "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", str(out)]
    else:
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(img),
               "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
               "-filter_complex", vf, "-t", str(dur), "-c:v", "libx264",
               "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def _mux(clip: Path, audio: Path | None, srt: Path | None, out: Path):
    vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
    if srt and srt.exists() and srt.read_text().strip():
        vf += _sub_filter(srt)
    cmd = ["ffmpeg", "-y", "-i", str(clip)]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-filter_complex", "[0:v]" + vf + "[v]", "-map", "[v]"]
    if audio:
        cmd += ["-map", "1:a", "-c:a", "aac", "-shortest"]
    else:
        cmd += ["-map", "0:a?", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


# ============================================================
# Endpoints
# ============================================================

class CharReq(BaseModel):
    description: str
    seed: int | None = None
    views: list[str] = ["front"]


class VidReq(BaseModel):
    char_prompt: str = ""
    seed: int | None = None        # None/0 -> auto random
    scene_prompt: str = ""
    image_id: str = ""             # /api/upload id — skips scene gen
    dialogue: str = ""
    voice: str = "female"          # female | male | none
    duration_s: float = 3.5        # 2.0 - 8.0
    engine: str = "auto"           # auto | wan | static
    uncensored: bool = False


@app.exception_handler(HTTPException)
async def http_exc(request, exc: HTTPException):
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": False, "error": {"code": exc.status_code,
                                                "message": exc.detail}},
                        status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def val_exc(request, exc):
    from fastapi.responses import JSONResponse
    print("422 on", request.url.path, exc.errors()[:3], flush=True)
    return JSONResponse({"ok": False, "error": {"code": 422,
                                                "message": "datos inválidos"}},
                        status_code=422)


@app.exception_handler(Exception)
async def any_exc(request, exc: Exception):
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": False, "error": {"code": 500,
                                                "message": str(exc)[:300]}},
                        status_code=500)


@app.post("/api/character")  # Pollinations
def character(req: CharReq):
    if not req.description.strip():
        raise HTTPException(400, "description is required")
    seed = req.seed if req.seed is not None else int.from_bytes(os.urandom(2), "big")
    wanted = [v for v in req.views if v in VIEW_PROMPTS] or ["front"]
    views = {v: f"/api/img?v={v}&p={urllib.parse.quote(_char_view_prompt(req.description, v))}&s={seed}"
             for v in wanted}
    return {"ok": True, "image_url": views[wanted[0]], "views": views,
            "seed": seed}


@app.get("/api/img")  # proxy a Pollinations (oculta el token)
def img_proxy(p: str, s: int, v: str = "front"):
    if not (0 < s <= 2**31) or len(p) > 2000:
        raise HTTPException(400, "bad params")
    out = WORK / "imgcache" / f"{uuid.uuid4().hex[:10]}.png"
    out.parent.mkdir(exist_ok=True)
    try:
        _dl_poll(p, s, out)
    except Exception as e:
        raise HTTPException(502, f"image gen failed: {e}")
    return FileResponse(out)


@app.post("/api/upload")
async def upload(request: Request):
    form = await request.form()
    f = form.get("file")
    if not f or not getattr(f, "filename", None):
        raise HTTPException(400, "file is required")
    data = await f.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "max 15MB")
    sig = data[:16]
    magic = (sig[:8] == b"\x89PNG\r\n\x1a\n" or sig[:2] == b"\xff\xd8"
             or sig[:4] == b"RIFF" or sig[4:12] in (b"ftypavif", b"ftypheic"))
    if not ((f.content_type or "").startswith("image/") or magic):
        raise HTTPException(400, "must be an image")
    uid = uuid.uuid4().hex[:10]
    src = UPLOADS / f"{uid}.src"
    src.write_bytes(data)
    dst = UPLOADS / f"{uid}.jpg"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                        "-vf", "scale='min(1080,iw)':-2", "-q:v", "3", str(dst)],
                       capture_output=True)
    if r.returncode != 0 or not dst.exists():
        dst = UPLOADS / f"{uid}{Path(f.filename).suffix or '.png'}"
        src.rename(dst)
    else:
        src.unlink(missing_ok=True)
    return {"ok": True, "image_id": uid, "url": f"/api/upload/{uid}"}


@app.get("/api/upload/{uid}")
def get_upload(uid: str):
    if not re.fullmatch(r"[0-9a-f]{10}", uid):
        raise HTTPException(404)
    for f in UPLOADS.glob(uid + ".*"):
        return FileResponse(f)
    raise HTTPException(404)


def _vreq_log(vid, req, status, err, t0, engine=None):
    if not SUPA_URL or not SUPA_KEY:
        return
    try:
        _rpc("vreq_log", {
            "p_video_id": vid, "p_char": req.char_prompt[:500],
            "p_scene": req.scene_prompt[:500],
            "p_dialogue": req.dialogue[:300], "p_engine": engine or req.engine,
            "p_voice": req.voice, "p_dur": req.duration_s,
            "p_unc": req.uncensored, "p_img": req.image_id,
            "p_status": status, "p_error": (err or "")[:500],
            "p_ms": int((time.time() - t0) * 1000)})
    except Exception as e:
        print("vreq_log failed:", e, flush=True)


# job_id -> {"status": "processing"|"ok"|"error", ...}. Un solo worker/instancia
# (ver Procfile), así que un dict en memoria basta; se limpia solo (ver _job_gc).
JOBS: dict[str, dict] = {}
JOB_TTL = 3600


def _job_gc():
    now = time.time()
    dead = [k for k, v in JOBS.items() if now - v.get("ts", now) > JOB_TTL]
    for k in dead:
        JOBS.pop(k, None)


@app.post("/api/video")  # Pollinations → Edge-TTS → Wan 2.2/Vidu/ffmpeg
async def video(req: VidReq):
    if not req.scene_prompt.strip():
        raise HTTPException(400, "scene_prompt is required")
    if not req.image_id and not req.char_prompt.strip():
        raise HTTPException(400, "char_prompt or image_id is required")
    if req.engine not in ("auto", "wan", "fal", "static"):
        raise HTTPException(400, "engine must be auto|wan|fal|static")
    if req.voice not in ("female", "male", "none"):
        raise HTTPException(400, "voice must be female|male|none")
    if req.image_id and not list(UPLOADS.glob(req.image_id + ".*")):
        raise HTTPException(404, "image_id not found")

    _job_gc()
    t0 = time.time()
    vid = uuid.uuid4().hex[:10]
    JOBS[vid] = {"status": "processing", "ts": t0}
    asyncio.create_task(_run_job(req, vid, t0))
    return {"ok": True, "video_id": vid, "status": "processing"}


@app.get("/api/video/{vid}/status")
async def video_status(vid: str):
    job = JOBS.get(vid)
    if not job:
        raise HTTPException(404, "job not found")
    return {"ok": job["status"] != "error", **job}


async def _run_job(req: VidReq, vid: str, t0: float):
    try:
        resp = await _video_inner(req, vid, t0)
        JOBS[vid] = {"status": "ok", "ts": time.time(), **resp}
    except HTTPException as e:
        _vreq_log(vid, req, f"error_{e.status_code}", str(e.detail), t0)
        JOBS[vid] = {"status": "error", "ts": time.time(),
                     "error": {"code": e.status_code, "message": e.detail}}
    except Exception as e:
        _vreq_log(vid, req, "error_500", str(e), t0)
        JOBS[vid] = {"status": "error", "ts": time.time(),
                     "error": {"code": 500, "message": str(e)[:300]}}


async def _video_inner(req: VidReq, vid: str, t0: float):
    if not req.seed or req.seed <= 0 or req.seed > 2**31:
        req.seed = random.randint(1, 2**31 - 1)
    dur_anim = min(max(req.duration_s, 2.0), 8.0)

    d = WORK / vid
    d.mkdir()
    img = d / "scene.png"
    if req.image_id:
        srcs = list(UPLOADS.glob(req.image_id + ".*"))
        if not srcs:
            raise HTTPException(404, "image_id not found")
        img = srcs[0]
    else:
        try:
            await asyncio.to_thread(
                _dl_poll, _scene_image_prompt(req.char_prompt, req.scene_prompt),
                req.seed, img)
        except Exception as e:
            raise HTTPException(502, f"image gen failed: {e}")

    audio = srt = None
    if req.dialogue.strip() and req.voice != "none":
        audio, srt = d / "v.mp3", d / "v.srt"
        await _tts(req.dialogue, audio, srt, req.voice)
        dur = max(4.0, len(req.dialogue) / 14.0)
    else:
        dur = 6.0

    out = d / "final.mp4"
    anim_err = None
    used_engine = None
    if req.engine in ("auto", "wan", "fal"):
        if req.engine == "fal":
            try:
                await asyncio.to_thread(_animate_fal, img, req.scene_prompt,
                                        d / "anim_fal.mp4", dur_anim)
                src = d / "anim_fal.mp4"
                if src.exists():
                    if audio or (srt and srt.exists() and srt.read_text().strip()):
                        await asyncio.to_thread(_mux, src, audio, srt, out)
                    else:
                        src.rename(out)
                    used_engine = "fal"
            except Exception as e:
                anim_err = f"fal: {e}"
        else:
            try:
                await asyncio.to_thread(_animate_wan, img, req.scene_prompt,
                                        d / "anim.mp4", req.seed, req.uncensored)
                src = d / "anim.mp4"
                if src.exists():
                    _motion_mark(True)
                    if audio or (srt and srt.exists() and srt.read_text().strip()):
                        await asyncio.to_thread(_mux, src, audio, srt, out)
                    else:
                        src.rename(out)
                    used_engine = "wan"
            except Exception as e:
                _motion_mark(False)
                anim_err = f"wan: {e}"
        if req.engine == "auto" and not out.exists() and KAGGLE_URL:
            try:
                await asyncio.to_thread(_animate_kaggle, img, req.scene_prompt,
                                        out, dur_anim)
                if out.exists():
                    used_engine = "kaggle"
            except Exception as e:
                anim_err = (anim_err or "") + f" kaggle: {e}"
        if req.engine == "auto" and not out.exists():
            try:
                await asyncio.to_thread(_animate_vidu, img, req.scene_prompt, out)
                if out.exists():
                    used_engine = "vidu"
            except Exception as e:
                anim_err = (anim_err or "") + f" vidu: {e}"
        if not out.exists() and req.engine in ("auto", "wan", "fal"):
            raise HTTPException(503, "motion_unavailable: " + (anim_err or "")[:300])
    if not out.exists():
        try:
            await asyncio.to_thread(_render, img, audio, srt, out, dur)
            used_engine = "static"
        except subprocess.CalledProcessError as e:
            raise HTTPException(500, "ffmpeg failed: " + e.stderr.decode()[-300:])
    await asyncio.to_thread(_store_video, vid, req.char_prompt,
                            req.scene_prompt, out)
    _vreq_log(vid, req, "ok", anim_err, t0, engine=used_engine)
    resp = {"ok": True, "video_id": vid,
            "download": f"/api/video/{vid}/final.mp4",
            "preview": f"/api/video/{vid}/preview.png",
            "engine_used": used_engine}
    if anim_err:
        resp["fallback"] = anim_err[:400]
    return resp


@app.get("/api/motion_status")
async def motion_status():
    return {"ok": True, "motion": await asyncio.to_thread(_motion_available)}


@app.get("/api/options")
def options():
    return {"ok": True,
            "voices": [{"id": "female", "label": "Femenina (Catalina, Chile)"},
                       {"id": "male", "label": "Masculina (Lorenzo, Chile)"},
                       {"id": "none", "label": "Sin voz"}],
            "engines": [{"id": "auto", "label": "Animación real (auto)"},
                        {"id": "fal", "label": "Animación pagada (fal.ai)"},
                        {"id": "wan", "label": "Solo Wan 2.2"},
                        {"id": "static", "label": "Solo imagen con cámara"}],
            "durations": [3.5, 5.0, 8.0]}


@app.get("/api/requests")
def request_log():
    try:
        rows = _rpc("vreq_list", {"lim": 50})
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "requests": rows}


@app.get("/api/feed")
def feed():
    _db_migrate()
    items = [{"video_id": i["video_id"],
              "url": f"/api/video/{i['video_id']}/final.mp4",
              "scene": i.get("scene", ""),
              "created_at": i.get("created_at", 0)}
             for i in _db_list(50)]
    return {"ok": True, "videos": items}


@app.delete("/api/video/{vid}")
async def del_video(vid: str):
    def _do():
        try:
            _supa_req("DELETE", f"object/videos/{vid}.mp4")
        except Exception:
            pass
        return _rpc("videos_delete", {"p_id": vid})
    rows = await asyncio.to_thread(_do)
    if not rows:
        raise HTTPException(404, "video not found")
    return {"ok": True}


@app.put("/api/video/{vid}")
async def upd_video(vid: str, req: Request):
    body = await req.json()
    rows = await asyncio.to_thread(_rpc, "videos_update",
                                   {"p_id": vid, "p_scene": body.get("scene")})
    if not rows:
        raise HTTPException(404, "video not found")
    return {"ok": True, "video": rows[0]}


@app.get("/api/video/{vid}/final.mp4")
def get_video(vid: str):
    if not re.fullmatch(r"[0-9a-f]{10}", vid):
        raise HTTPException(404)
    if _supa_has(vid):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(_supa_public(vid))
    f = WORK / vid / "final.mp4"
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, media_type="video/mp4", filename="nova-video.mp4")


@app.get("/api/video/{vid}/preview.png")
def get_preview(vid: str):
    if not re.fullmatch(r"[0-9a-f]{10}", vid):
        raise HTTPException(404)
    f = WORK / vid / "scene.png"
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, media_type="image/png")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
