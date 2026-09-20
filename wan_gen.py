"""Image-to-video via Wan 2.2 Lightning HF Space (ZeroGPU) — plain HTTP.

Uses the Gradio queue API directly (no gradio_client, no websockets):
  POST {base}/gradio_api/upload           -> server file path
  POST {base}/gradio_api/call/<fn>        -> {"event_id": ...}
  GET  {base}/gradio_api/call/<fn>/<eid>  -> SSE stream until "event: complete"
"""
import json
import mimetypes
import os
import urllib.request
import uuid
from pathlib import Path

BASE = "https://saravutw-wan2-2-i2v-lightning-4-8step-custom.hf.space"
NEG = ("blurry, low quality, chaotic, deformed, watermark, bad anatomy, "
       "shaky camera view point")


def _req(url, data=None, headers=None, timeout=60):
    r = urllib.request.Request(url, data=data,
                               headers=headers or {"User-Agent": "nova-studio"})
    return urllib.request.urlopen(r, timeout=timeout)


def _upload(img_path: Path) -> str:
    boundary = uuid.uuid4().hex
    body = (b"--" + boundary.encode() + b'\r\nContent-Disposition: form-data; '
            b'name="files"; filename="' + img_path.name.encode() + b'"\r\n'
            b"Content-Type: " + mimetypes.guess_type(img_path.name)[0].encode()
            + b"\r\n\r\n" + img_path.read_bytes() + b"\r\n--" + boundary.encode()
            + b"--\r\n")
    r = _req(BASE + "/gradio_api/upload", body,
             {"Content-Type": "multipart/form-data; boundary=" + boundary},
             timeout=120)
    return json.loads(r.read())[0]


def generate(image_path: str, motion_prompt: str, out_mp4: str,
             seed: int = 42, duration_s: float = 3.5,
             safe_mode: bool = True) -> str:
    token = os.environ.get("HF_TOKEN")
    hdrs = {"User-Agent": "nova-studio", "Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = "Bearer " + token
    server_path = _upload(Path(image_path))
    img = {"path": server_path, "url": BASE + "/gradio_api/file=" + server_path,
           "orig_name": Path(image_path).name, "meta": {"_type": "gradio.FileData"}}
    data = [img, None, motion_prompt, 4, NEG, duration_s, 1, 1,
            seed, False, 5, "UniPCMultistep", 3.0, 16, safe_mode, True]
    r = _req(BASE + "/gradio_api/call/generate_video",
             json.dumps({"data": data}).encode(), hdrs, timeout=60)
    event_id = json.loads(r.read())["event_id"]

    video_url = None
    with _req(f"{BASE}/gradio_api/call/generate_video/{event_id}",
              headers=hdrs, timeout=300) as stream:
        for raw in stream:
            line = raw.decode(errors="replace").strip()
            if line.startswith("event: error"):
                raise RuntimeError("space returned error")
            if line.startswith("data:") and line[5:].strip() not in ("null", ""):
                try:
                    payload = json.loads(line[5:])
                    item = payload[0]
                    if isinstance(item, dict):
                        video_url = item.get("url") or item.get("path")
                    elif isinstance(item, str):
                        video_url = item
                except Exception:
                    continue
    if not video_url:
        raise RuntimeError("no video in space response")
    if video_url.startswith("/"):
        video_url = BASE + video_url
    elif not video_url.startswith("http"):
        video_url = BASE + "/gradio_api/file=" + video_url
    with _req(video_url, headers=hdrs, timeout=120) as r, open(out_mp4, "wb") as f:
        f.write(r.read())
    return out_mp4
