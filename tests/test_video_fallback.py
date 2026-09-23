"""Unit tests for the engine fallback chain in main._video_inner.

Scope: engine="auto" tries wan -> kaggle (if KAGGLE_URL set) -> vidu -> static
(_render), accumulating failures into `anim_err` (returned to the client as
resp["fallback"]) and recording which one succeeded in `resp["engine_used"]`.
An explicit engine="wan"/"fal" does NOT fall back to other engines — a
failure there surfaces as a 503 instead of silently trying something else.
All external calls (_animate_*, _render, _dl_poll, _tts, _store_video,
_vreq_log) are mocked; no real network/ffmpeg/playwright call is made.
"""
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

import main
from conftest import make_req


def run(coro):
    return asyncio.run(coro)


def test_auto_wan_success(work_dir, no_network):
    """engine=auto, wan succeeds on the first try: only wan is called, no
    fallback recorded, response is ok."""
    def wan_ok(img, scene_prompt, out, seed, uncensored=False):
        out.write_bytes(b"wan-video")
    main._animate_wan.side_effect = wan_ok

    req = make_req(engine="auto")
    resp = run(main._video_inner(req, "vid_wan_ok", 0.0))

    assert resp["ok"] is True
    assert "fallback" not in resp
    main._animate_wan.assert_called_once()
    main._animate_kaggle.assert_not_called()
    main._animate_vidu.assert_not_called()
    main._render.assert_not_called()


def test_auto_wan_fails_kaggle_succeeds(work_dir, no_network):
    """engine=auto, wan fails, KAGGLE_URL configured and kaggle succeeds:
    vidu must not even be attempted, and the wan error is surfaced in
    resp['fallback']."""
    main.KAGGLE_URL = "https://fake-kaggle.example"

    def kaggle_ok(img, scene_prompt, out, seconds):
        out.write_bytes(b"kaggle-video")
    main._animate_kaggle.side_effect = kaggle_ok

    req = make_req(engine="auto")
    resp = run(main._video_inner(req, "vid_kaggle_ok", 0.0))

    assert resp["ok"] is True
    assert "wan:" in resp["fallback"]
    main._animate_wan.assert_called_once()
    main._animate_kaggle.assert_called_once()
    main._animate_vidu.assert_not_called()
    main._render.assert_not_called()


def test_auto_all_engines_fail_falls_back_to_static(work_dir, no_network):
    """engine=auto, wan/kaggle/vidu all fail: falls back to _render/static
    instead of raising 503, matching the documented "auto -> wan -> kaggle ->
    vidu -> static" fallback chain. Previously this raised HTTPException 503
    without ever calling _render — fixed so `auto` only surfaces a 503 when
    even the static fallback itself fails (see next test)."""
    main.KAGGLE_URL = "https://fake-kaggle.example"
    # wan/kaggle/vidu already fail via the no_network fixture defaults.
    main._render.side_effect = lambda img, audio, srt, out, dur: Path(out).write_bytes(b"fake-static-mp4")

    req = make_req(engine="auto")
    resp = run(main._video_inner(req, "vid_all_fail", 0.0))

    assert resp["ok"] is True
    assert resp["engine_used"] == "static"
    assert "fallback" in resp  # wan/kaggle/vidu errors are still surfaced
    main._animate_wan.assert_called_once()
    main._animate_kaggle.assert_called_once()
    main._animate_vidu.assert_called_once()
    main._render.assert_called_once()


def test_engine_wan_only_raises_503_without_static_fallback(work_dir, no_network):
    """engine="wan" (not auto): if wan fails, it must NOT silently fall back
    to kaggle/vidu/static — the user explicitly asked for wan only, so a
    failure surfaces as a 503."""
    req = make_req(engine="wan")
    with pytest.raises(HTTPException) as exc_info:
        run(main._video_inner(req, "vid_wan_only_fail", 0.0))

    assert exc_info.value.status_code == 503
    main._animate_wan.assert_called_once()
    main._animate_kaggle.assert_not_called()
    main._animate_vidu.assert_not_called()
    main._render.assert_not_called()


def test_engine_static_uses_render_directly(work_dir, no_network):
    """engine=static skips the whole wan/kaggle/vidu block (L711 guard) and
    goes straight to _render — this is the only way _render is reached in
    the current code."""
    def render_ok(img, audio, srt, out, dur):
        out.write_bytes(b"static-video")
    main._render.side_effect = render_ok

    req = make_req(engine="static")
    resp = run(main._video_inner(req, "vid_static", 0.0))

    assert resp["ok"] is True
    assert "fallback" not in resp
    main._animate_wan.assert_not_called()
    main._animate_kaggle.assert_not_called()
    main._animate_vidu.assert_not_called()
    main._render.assert_called_once()
