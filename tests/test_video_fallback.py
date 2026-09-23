"""Unit tests for the engine fallback chain in main._video_inner.

Scope: engine="auto" should try wan -> kaggle (if KAGGLE_URL set) -> vidu,
accumulating failures into `anim_err` (returned to the client as
resp["fallback"]). All external calls (_animate_*, _render, _dl_poll, _tts,
_store_video, _vreq_log) are mocked; no real network/ffmpeg/playwright call
is made.

IMPORTANT — a finding, not a test-writing mistake: the current main.py does
NOT expose a `used_engine` field on the response, and when engine="auto" and
every real-motion engine (wan/kaggle/vidu) fails, `_video_inner` does *not*
fall back to `_render` (the static/ffmpeg path). Instead it raises
HTTPException(503) at main.py L749-750, before the `_render` fallback block
at L751 is ever reached for engine in ("auto", "wan", "fal"). The `_render`
fallback is only reachable when engine="static" from the start (the block at
L711 is skipped entirely for that engine). See test
`test_auto_all_engines_fail_raises_503_no_static_fallback` and
`test_engine_static_uses_render_directly` below, and the final QA report for
details.
"""
import asyncio

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


def test_auto_all_engines_fail_raises_503_no_static_fallback(work_dir, no_network):
    """engine=auto, wan/kaggle/vidu all fail: main.py raises HTTPException
    503 (L749-750) instead of falling back to _render/static. This
    contradicts the "vidu/static as fallback for engine=auto" description in
    the repo's own README-level summary — documented as a finding, not
    asserted away. `_render` must never be called in this path."""
    main.KAGGLE_URL = "https://fake-kaggle.example"
    # wan/kaggle/vidu already fail via the no_network fixture defaults.

    req = make_req(engine="auto")
    with pytest.raises(HTTPException) as exc_info:
        run(main._video_inner(req, "vid_all_fail", 0.0))

    assert exc_info.value.status_code == 503
    main._animate_wan.assert_called_once()
    main._animate_kaggle.assert_called_once()
    main._animate_vidu.assert_called_once()
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
