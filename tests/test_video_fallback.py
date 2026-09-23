"""Unit tests for the engine fallback chain in main._video_inner.

Scope: engine="auto" tries every real AI motion engine in order — wan ->
kaggle (if KAGGLE_URL set) -> vidu — accumulating failures into `anim_err`
(returned to the client as resp["fallback"]) and recording which one
succeeded in `resp["engine_used"]`. `static` (camera pan over the still
image, no AI movement) is deliberately NOT part of the "auto" chain and is
only used when the caller explicitly asks for engine="static" — "auto" must
raise a 503 rather than silently downgrade to a non-AI result. An explicit
engine="wan"/"fal" also does NOT fall back to other engines — a failure
there surfaces as a 503 instead of silently trying something else. All
external calls (_animate_*, _render, _dl_poll, _tts, _store_video,
_vreq_log) are mocked; no real network/ffmpeg/playwright call is made.
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


def test_auto_all_engines_fail_raises_503_never_uses_static(work_dir, no_network):
    """engine=auto, wan/kaggle/vidu all fail: raises HTTPException 503.
    `static` has no AI movement, so "auto" must never silently downgrade to
    it — `_render` must not be called."""
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


def test_duplicate_output_triggers_retry_with_fresh_seed(work_dir, no_network):
    """If wan produces a video byte-identical to the previous one (the
    duplicate-video bug), _video_inner must retry wan once automatically
    before returning — the retry here succeeds with different content, so
    the response must reflect the retried (different) video, not the
    original duplicate."""
    import hashlib
    calls = []

    def side_effect(img, scene_prompt, out, seed, uncensored=False):
        calls.append(seed)
        if len(calls) == 1:
            out.write_bytes(b"same-bytes-as-last-time")
        else:
            out.write_bytes(b"different-bytes-this-time")
    main._animate_wan.side_effect = side_effect

    # Prime _LAST_MOTION_HASH as if a previous video already produced the
    # exact content the first (duplicate) call is about to write.
    main._LAST_MOTION_HASH = hashlib.sha256(b"same-bytes-as-last-time").hexdigest()

    req = make_req(engine="auto")

    resp = run(main._video_inner(req, "vid_dup_retry", 0.0))

    assert resp["ok"] is True
    assert main._animate_wan.call_count == 2
    # each call must use a different seed (the whole point of the retry)
    assert calls[0] != calls[1]
    assert main._LAST_MOTION_HASH == hashlib.sha256(b"different-bytes-this-time").hexdigest()


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
