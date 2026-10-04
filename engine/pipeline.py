"""Streaming pipeline and video encoder.

Orchestrates the loop: step the symbolic scene -> compute sparse delta ->
compose the frame in place -> hand the finished frame to the encoder.
Raw pixel frames are never accumulated: memory stays flat O(1) whether the
clip has 10 frames or 10,000.
"""
from __future__ import annotations

import subprocess

from engine.renderer import SparseRenderer
from engine.scene import SceneGraph


class VideoPipeline:
    def __init__(self, width: int, height: int, fps: int) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.renderer = SparseRenderer(width, height)
        self._keyframe_done = False

    def generate_frame(self, scene: SceneGraph):
        """Compose the next frame in place and return the shared buffer."""
        if not self._keyframe_done:
            self.renderer.render_keyframe(scene)
            self._keyframe_done = True
        else:
            delta = self.renderer.compute_delta(scene)
            if delta.modified_pixel_count:
                self.renderer.apply_delta_in_place(delta)
        return self.renderer.get_current_frame()

    def export_mp4(self, scene: SceneGraph, n_frames: int, out_path: str) -> str:
        """Render `n_frames` into an MP4 by piping raw frames to ffmpeg.

        Only the pre-allocated master buffer exists at any moment; each
        frame is serialized straight into ffmpeg's stdin.
        """
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "-",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            out_path,
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            proc.stdin.write(self.generate_frame(scene).tobytes())
            dt = 1.0 / self.fps
            for _ in range(n_frames - 1):
                scene.step(dt)
                proc.stdin.write(self.generate_frame(scene).tobytes())
        finally:
            proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg failed while encoding " + out_path)
        return out_path
