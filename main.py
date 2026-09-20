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

# Consistent voice for characters (Chilean Spanish female by default)
VOICES = {"female": "es-CL-CatalinaNeural", "male": "es-CL-LorenzoNeural"}
POLL = "https://image.pollinations.ai/prompt/{p}?width=720&height=1280&nologo=true&seed={s}"


class CharReq(BaseModel):
    description: str
    seed: int | None = None


@app.post("/api/character")
def character(req: CharReq):
    seed = req.seed if req.seed is not None else int.from_bytes(os.urandom(2), "big")
    prompt = urllib.parse.quote(
        "photorealistic candid phone selfie, " + req.description
        + ", natural skin texture, imperfect, soft indoor light")
    return {"image_url": POLL.format(p=prompt, s=seed), "seed": seed}


class VidReq(BaseModel):
    char_prompt: str
    seed: int
    scene_prompt: str
    dialogue: str = ""
    voice: str = "female"
    animate: bool = True


def _dl(url: str, out: Path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as f:
        f.write(r.read())


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


def _render(img: Path, audio: Path | None, srt: Path | None, out: Path, dur: float):
    frames = int(dur * 30)
    step = 0.18 / frames
    vf = ("scale=2048:3072,zoompan=z='min(zoom+%.6f,1.18)':"
          "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=1080x1920:fps=30" % (step, frames))
    if srt and srt.exists() and srt.read_text().strip():
        sub = str(srt).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        vf += ",subtitles='%s':force_style='FontName=DejaVu Sans,FontSize=14,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,Alignment=2,MarginV=340'" % sub
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(img)]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-filter_complex", vf, "-t", str(dur), "-c:v", "libx264",
            "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-c:a", "aac", "-shortest"]
        # reorder: anullsrc must be an input; rebuild
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(img),
               "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
               "-filter_complex", vf, "-t", str(dur), "-c:v", "libx264",
               "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest"]
    cmd.append(str(out))
    subprocess.run(cmd, check=True, capture_output=True)


@app.post("/api/video")
async def video(req: VidReq):
    vid = uuid.uuid4().hex[:10]
    d = WORK / vid
    d.mkdir()
    img = d / "scene.png"
    # scene image keeps character via same seed + character description
    p = urllib.parse.quote(
        "photorealistic candid phone photo, " + req.char_prompt + ", "
        + req.scene_prompt + ", natural skin, imperfect, indoor light")
    try:
        await asyncio.to_thread(_dl, POLL.format(p=p, s=req.seed), img)
    except Exception as e:
        raise HTTPException(502, f"image gen failed: {e}")

    audio = srt = None
    if req.dialogue.strip():
        audio, srt = d / "v.mp3", d / "v.srt"
        await _tts(req.dialogue, audio, srt, req.voice)
        dur = max(4.0, len(req.dialogue) / 14.0)
    else:
        dur = 6.0

    out = d / "final.mp4"
    vidu_err = None
    if req.animate:
        try:
            import vidu_gen
            await asyncio.to_thread(vidu_gen.generate_sync, img, req.scene_prompt, out)
        except Exception as e:
            vidu_err = str(e)
            out = None
    if out is None or not (d / "final.mp4").exists():
        try:
            await asyncio.to_thread(_render, img, audio, srt, d / "final.mp4", dur)
        except subprocess.CalledProcessError as e:
            raise HTTPException(500, "ffmpeg failed: " + e.stderr.decode()[-300:])
    resp = {"video_id": vid, "download": f"/api/video/{vid}/final.mp4"}
    if vidu_err:
        resp["fallback"] = vidu_err
    return resp


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
