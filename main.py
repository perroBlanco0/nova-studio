import asyncio
import os
import re
import subprocess
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

WORK = Path("/tmp/novavids")
WORK.mkdir(exist_ok=True)


# ============================================================
# Platform: Pollinations.ai — imagen de personaje y escena
# ============================================================

POLL = "https://image.pollinations.ai/prompt/{p}?width=720&height=1280&nologo=true&seed={s}"


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


def _dl(url: str, out: Path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as f:
        f.write(r.read())


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


def _animate_wan(img: Path, scene_prompt: str, out: Path, seed: int):
    import wan_gen
    motion = ("natural body motion, subtle movement, "
              + scene_prompt + ", cinematic")
    wan_gen.generate(str(img), motion, str(out), seed)


# ============================================================
# Platform: Vidu — video img2video de respaldo (solo VM) — vidu_gen.py
# ============================================================


def _animate_vidu(img: Path, scene_prompt: str, out: Path):
    import vidu_gen
    vidu_gen.generate_sync(img, scene_prompt, out)


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
    vf = ("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
          "zoompan=z='min(zoom+%.6f,1.15)':"
          "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=1080x1920:fps=24" % (step, frames))
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
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
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
    dialogue: str = ""
    voice: str = "female"          # female | male | none
    duration_s: float = 3.5        # 2.0 - 8.0
    engine: str = "auto"           # auto | wan | static


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
    views = {v: POLL.format(p=_char_view_prompt(req.description, v), s=seed)
             for v in wanted}
    return {"ok": True, "image_url": views[wanted[0]], "views": views,
            "seed": seed}


@app.post("/api/video")  # Pollinations → Edge-TTS → Wan 2.2/Vidu/ffmpeg
async def video(req: VidReq):
    if not req.char_prompt.strip() or not req.scene_prompt.strip():
        raise HTTPException(400, "char_prompt and scene_prompt are required")
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
    try:
        await asyncio.to_thread(
            _dl, POLL.format(p=_scene_image_prompt(req.char_prompt, req.scene_prompt),
                             s=req.seed), img)
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
                                    d / "anim.mp4", req.seed)
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
    resp = {"ok": True, "video_id": vid,
            "download": f"/api/video/{vid}/final.mp4",
            "preview": f"/api/video/{vid}/preview.png"}
    if anim_err:
        resp["fallback"] = anim_err[:400]
    return resp


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


@app.get("/api/video/{vid}/final.mp4")
def get_video(vid: str):
    if not re.fullmatch(r"[0-9a-f]{10}", vid):
        raise HTTPException(404)
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
