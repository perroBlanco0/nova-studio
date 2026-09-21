import asyncio
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import edge_tts
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

WORK = Path("/tmp/novavids")
WORK.mkdir(exist_ok=True)
UPLOADS = WORK / "uploads"
UPLOADS.mkdir(exist_ok=True)


# ============================================================
# Persistencia: MongoDB + GridFS (opcional, via MONGO_URI)
# ============================================================

GRIDFS_LIMIT = 400 * 1024 * 1024
_fs = None
_vids = None
try:
    if os.environ.get("MONGO_URI"):
        import gridfs
        from pymongo import MongoClient
        _mc = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=5000)
        _db = _mc.get_default_database()
        _fs = gridfs.GridFS(_db)
        _vids = _db["videos"]
except Exception:
    _fs = _vids = None


def _store_video(vid: str, char_prompt: str, scene_prompt: str, mp4: Path):
    if _fs is None or _vids is None:
        return
    try:
        fid = _fs.put(mp4.read_bytes(), filename=f"{vid}/final.mp4",
                      contentType="video/mp4")
        _vids.insert_one({"video_id": vid, "file_id": fid,
                          "char_prompt": char_prompt,
                          "scene_prompt": scene_prompt,
                          "created_at": time.time()})
        while _total_gridfs_bytes() > GRIDFS_LIMIT:
            d = _db["fs.files"].find_one({}, sort=[("uploadDate", 1)])
            if not d:
                break
            _fs.delete(d["_id"])
            _vids.delete_one({"file_id": d["_id"]})
    except Exception:
        pass


def _total_gridfs_bytes() -> int:
    try:
        agg = _db["fs.files"].aggregate(
            [{"$group": {"_id": None, "t": {"$sum": "$length"}}}])
        return next(agg)["t"]
    except Exception:
        return 0


def _gridfs_video(vid: str):
    if _vids is None or _fs is None:
        return None
    try:
        doc = _vids.find_one({"video_id": vid})
        if doc:
            return _fs.get(doc["file_id"]).read()
    except Exception:
        pass
    return None


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


_MOTION_CACHE = {"ts": 0.0, "ok": False}


def _motion_available() -> bool:
    now = time.time()
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
    char_prompt: str
    seed: int
    scene_prompt: str
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


@app.post("/api/video")  # Pollinations → Edge-TTS → Wan 2.2/Vidu/ffmpeg
async def video(req: VidReq):
    if not req.scene_prompt.strip():
        raise HTTPException(400, "scene_prompt is required")
    if not req.image_id and not req.char_prompt.strip():
        raise HTTPException(400, "char_prompt or image_id is required")
    if req.engine not in ("auto", "wan", "static"):
        raise HTTPException(400, "engine must be auto|wan|static")
    if req.voice not in ("female", "male", "none"):
        raise HTTPException(400, "voice must be female|male|none")
    if not (0 < req.seed <= 2**31):
        raise HTTPException(400, "seed must be a positive integer")
    dur_anim = min(max(req.duration_s, 2.0), 8.0)

    vid = uuid.uuid4().hex[:10]
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
    if req.engine in ("auto", "wan"):
        try:
            await asyncio.to_thread(_animate_wan, img, req.scene_prompt,
                                    d / "anim.mp4", req.seed, req.uncensored)
            src = d / "anim.mp4"
            if src.exists():
                if audio or (srt and srt.exists() and srt.read_text().strip()):
                    await asyncio.to_thread(_mux, src, audio, srt, out)
                else:
                    src.rename(out)
        except Exception as e:
            anim_err = f"wan: {e}"
        if req.engine == "auto" and not out.exists():
            try:
                await asyncio.to_thread(_animate_vidu, img, req.scene_prompt, out)
            except Exception as e:
                anim_err = (anim_err or "") + f" vidu: {e}"
    if not out.exists():
        try:
            await asyncio.to_thread(_render, img, audio, srt, out, dur)
        except subprocess.CalledProcessError as e:
            raise HTTPException(500, "ffmpeg failed: " + e.stderr.decode()[-300:])
    await asyncio.to_thread(_store_video, vid, req.char_prompt,
                            req.scene_prompt, out)
    resp = {"ok": True, "video_id": vid,
            "download": f"/api/video/{vid}/final.mp4",
            "preview": f"/api/video/{vid}/preview.png"}
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
                        {"id": "wan", "label": "Solo Wan 2.2"},
                        {"id": "static", "label": "Solo imagen con cámara"}],
            "durations": [3.5, 5.0, 8.0]}


@app.get("/api/feed")
def feed():
    items = []
    if _vids is not None:
        try:
            for doc in _vids.find({}, {"_id": 0}).sort("created_at", -1).limit(20):
                items.append({
                    "video_id": doc["video_id"],
                    "url": f"/api/video/{doc['video_id']}/final.mp4",
                    "scene": doc.get("scene_prompt", ""),
                    "created_at": doc.get("created_at", 0)})
        except Exception:
            items = []
    return {"ok": True, "videos": items}


@app.get("/api/video/{vid}/final.mp4")
def get_video(vid: str):
    if not re.fullmatch(r"[0-9a-f]{10}", vid):
        raise HTTPException(404)
    data = _gridfs_video(vid)
    if data is not None:
        from fastapi.responses import Response
        return Response(data, media_type="video/mp4")
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
