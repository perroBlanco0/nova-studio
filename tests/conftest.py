"""Shared pytest fixtures for the nova-studio test suite.

These tests import `main` directly (no HTTP server, no TestClient) so that
`_video_inner` can be exercised as a plain coroutine with every network- or
subprocess-touching dependency mocked out. Nothing here should ever open a
real socket or spawn ffmpeg/playwright/etc.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402  (import after sys.path tweak)


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    """Redirect main.WORK to an isolated temp dir so tests never touch
    /tmp/novavids or leave artifacts behind."""
    d = tmp_path / "novavids"
    d.mkdir()
    monkeypatch.setattr(main, "WORK", d)
    return d


@pytest.fixture
def no_network(monkeypatch):
    """Block every real network/subprocess call that _video_inner can reach,
    regardless of which branch a given test exercises. Individual tests
    override _animate_* / _render as needed to simulate success/failure.
    """
    def _fake_dl_poll(prompt, seed, out, negative=""):
        Path(out).write_bytes(b"fake-image-bytes")

    monkeypatch.setattr(main, "_dl_poll", Mock(side_effect=_fake_dl_poll))
    monkeypatch.setattr(main, "_tts", AsyncMock())
    monkeypatch.setattr(main, "_store_video", Mock())
    monkeypatch.setattr(main, "_vreq_log", Mock())
    monkeypatch.setattr(main, "_motion_mark", Mock())

    # Engines default to "always fail" unless a test overrides them — this
    # ensures a test that forgets to configure an engine can't accidentally
    # hit real network code.
    monkeypatch.setattr(main, "_animate_wan",
                        Mock(side_effect=RuntimeError("no mock configured: wan")))
    monkeypatch.setattr(main, "_animate_fal",
                        Mock(side_effect=RuntimeError("no mock configured: fal")))
    monkeypatch.setattr(main, "_animate_kaggle",
                        Mock(side_effect=RuntimeError("no mock configured: kaggle")))
    monkeypatch.setattr(main, "_animate_vidu",
                        Mock(side_effect=RuntimeError("no mock configured: vidu")))
    monkeypatch.setattr(main, "_render",
                        Mock(side_effect=RuntimeError("no mock configured: render")))
    monkeypatch.setattr(main, "KAGGLE_URL", "")
    monkeypatch.setattr(main, "_LAST_MOTION_HASH", None)
    return monkeypatch


def make_req(**overrides):
    kwargs = dict(char_prompt="a person", scene_prompt="waving at camera",
                  dialogue="", voice="none", duration_s=3.5, engine="auto")
    kwargs.update(overrides)
    return main.VidReq(**kwargs)
