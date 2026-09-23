"""Minimal plain-HTTP Gradio queue client for Wan i2v Spaces (zero-auth)."""
import json
import mimetypes
import urllib.request
import uuid
from pathlib import Path


def _req(url, data=None, headers=None, timeout=60):
    r = urllib.request.Request(url, data=data,
                               headers=headers or {"User-Agent": "nova-studio"})
    return urllib.request.urlopen(r, timeout=timeout)


def upload(base: str, img_path: str) -> str:
    p = Path(img_path)
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    body = (b"--" + boundary.encode() + b'\r\nContent-Disposition: form-data; '
            b'name="files"; filename="' + p.name.encode() + b'"\r\n'
            b"Content-Type: " + content_type.encode()
            + b"\r\n\r\n" + p.read_bytes() + b"\r\n--" + boundary.encode()
            + b"--\r\n")
    r = _req(base + "/gradio_api/upload", body,
             {"Content-Type": "multipart/form-data; boundary=" + boundary},
             timeout=120)
    return json.loads(r.read())[0]


def img_obj(base: str, server_path: str, name: str) -> dict:
    return {"path": server_path,
            "url": base + "/gradio_api/file=" + server_path,
            "orig_name": name,
            "meta": {"_type": "gradio.FileData"}}


def call_sse(base: str, fn: str, data: list, timeout=600) -> str:
    hdrs = {"User-Agent": "nova-studio", "Content-Type": "application/json"}
    r = _req(base + "/gradio_api/call" + fn,
             json.dumps({"data": data}).encode(), hdrs, timeout=60)
    event_id = json.loads(r.read())["event_id"]
    video_url = None
    with _req(f"{base}/gradio_api/call{fn}/{event_id}",
              headers=hdrs, timeout=timeout) as stream:
        for raw in stream:
            line = raw.decode(errors="replace").strip()
            if line.startswith("event: error"):
                raise RuntimeError("space returned error: " + line)
            if line.startswith("data:") and line[5:].strip() not in ("null", ""):
                try:
                    payload = json.loads(line[5:])
                    if not isinstance(payload, list):
                        continue
                    item = payload[0]
                    if isinstance(item, dict):
                        video_url = (item.get("url") or item.get("path")
                                     or (item.get("video") or {}).get("url"))
                    elif isinstance(item, str):
                        video_url = item
                    elif isinstance(item, list) and item:
                        sub = item[0]
                        if isinstance(sub, dict):
                            video_url = sub.get("url") or sub.get("path")
                except Exception:
                    continue
    if not video_url:
        raise RuntimeError("no video in space response")
    if video_url.startswith("/"):
        video_url = base + video_url
    elif not video_url.startswith("http"):
        video_url = base + "/gradio_api/file=" + video_url
    return video_url


def download(url: str, out: str):
    with _req(url, headers={"User-Agent": "nova-studio"},
              timeout=120) as r, open(out, "wb") as f:
        f.write(r.read())
