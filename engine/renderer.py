"""Sparse difference renderer.

One pre-allocated master frame buffer lives for the whole pipeline
lifecycle. `render_keyframe` fills it completely once (I-frame); every
subsequent frame only re-rasterizes the bounding boxes of entities whose
state changed since the last render (P-frames / deltas) and writes them
in place. Stationary state produces a zero-pixel delta and skips
rasterization entirely.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field

import numpy as np

from engine.scene import Entity, SceneGraph


@dataclass
class FrameDelta:
    """The changed regions of a frame, plus their rasterized pixels."""

    bounding_boxes: list[tuple[int, int, int, int]] = field(default_factory=list)
    patches: list[np.ndarray] = field(default_factory=list)
    modified_pixel_count: int = 0


def _entity_color(entity_id: str) -> tuple[float, float, float]:
    """Stable pseudo-random color per entity id (crc32, not salted hash())."""
    h = zlib.crc32(entity_id.encode("utf-8"))
    return (64 + h % 160, 64 + (h >> 8) % 160, 64 + (h >> 16) % 160)


class SparseRenderer:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._frame = np.zeros((height, width, 3), dtype=np.uint8)
        self._prev_entities: dict[str, tuple] = {}
        self._prev_light: tuple | None = None

    # -- public API ---------------------------------------------------------

    def render_keyframe(self, scene: SceneGraph) -> np.ndarray:
        """Rasterize the full scene into the master buffer (I-frame)."""
        self._frame[:] = self._raster_region(scene, 0, 0, self.width, self.height)
        self._remember(scene)
        return self._frame

    def compute_delta(self, scene: SceneGraph) -> FrameDelta:
        """Detect changed bounding boxes vs the last rendered state."""
        boxes: list[tuple[int, int, int, int]] = []
        light_key = scene.light.state_key() if scene.light is not None else None

        if light_key != self._prev_light:
            # Lighting moved or changed intensity: the whole canvas is affected.
            boxes = [(0, 0, self.width, self.height)]
        else:
            for entity in scene.entities.values():
                prev = self._prev_entities.get(entity.id)
                if prev is None:
                    box = self._clip(*entity.aabb())
                    if box:
                        boxes.append(box)
                elif prev != entity.state_key():
                    box = self._clip(*self._union_aabb(prev, entity))
                    if box:
                        boxes.append(box)
            for entity_id in self._prev_entities.keys() - scene.entities.keys():
                # Entity removed: clear the region it used to occupy.
                prev_pos, _prev_vel, prev_radius = self._prev_entities[entity_id]
                ghost = Entity(entity_id, prev_pos, (0.0, 0.0, 0.0), prev_radius)
                box = self._clip(*ghost.aabb())
                if box:
                    boxes.append(box)

        patches = [self._raster_region(scene, x, y, w, h) for x, y, w, h in boxes]
        self._remember(scene)
        return FrameDelta(
            bounding_boxes=boxes,
            patches=patches,
            modified_pixel_count=sum(w * h for _x, _y, w, h in boxes),
        )

    def apply_delta_in_place(self, delta: FrameDelta) -> None:
        """Write delta patches into the master buffer. Never reallocates it."""
        for (x, y, w, h), patch in zip(delta.bounding_boxes, delta.patches):
            self._frame[y:y + h, x:x + w] = patch

    def get_current_frame(self) -> np.ndarray:
        return self._frame

    def frame_buffer_ptr(self) -> int:
        return self._frame.ctypes.data

    # -- internals ----------------------------------------------------------

    def _remember(self, scene: SceneGraph) -> None:
        self._prev_entities = {e.id: e.state_key() for e in scene.entities.values()}
        self._prev_light = scene.light.state_key() if scene.light is not None else None

    def _clip(self, x0: int, y0: int, x1: int, y1: int):
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(self.width, x1)
        y1 = min(self.height, y1)
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1 - x0, y1 - y0)

    @staticmethod
    def _union_aabb(prev_state: tuple, entity: Entity) -> tuple[int, int, int, int]:
        """Union of the entity's previous and current bounding boxes."""
        prev_pos, _vel, prev_radius = prev_state
        px, py, _pz = prev_pos
        import math
        old = (
            math.floor(px - prev_radius),
            math.floor(py - prev_radius),
            math.ceil(px + prev_radius),
            math.ceil(py + prev_radius),
        )
        new = entity.aabb()
        return (
            min(old[0], new[0]),
            min(old[1], new[1]),
            max(old[2], new[2]),
            max(old[3], new[3]),
        )

    def _raster_region(self, scene: SceneGraph, x: int, y: int, w: int, h: int) -> np.ndarray:
        """Rasterize one rectangular region of the scene.

        Pure function of the world state: the same region of the same scene
        always produces the same pixels, so delta patches blend seamlessly
        into the keyframe.
        """
        xs = np.arange(x, x + w, dtype=np.float64)[None, :]
        ys = np.arange(y, y + h, dtype=np.float64)[:, None]

        if scene.light is not None:
            lx, ly = scene.light.pos[0], scene.light.pos[1]
            intensity = scene.light.intensity
        else:
            lx, ly, intensity = self.width / 2.0, self.height / 2.0, 1.0

        dist = np.sqrt((xs - lx) ** 2 + (ys - ly) ** 2)
        shade = intensity / (1.0 + (dist / 350.0) ** 2)

        base = 24.0 + 200.0 * shade
        region = np.empty((h, w, 3), dtype=np.float64)
        region[..., 0] = base * 0.35
        region[..., 1] = base * 0.45
        region[..., 2] = base * 0.75

        glow = 0.4 + 0.6 * shade
        for entity in scene.entities.values():
            cx, cy = entity.pos[0], entity.pos[1]
            r = entity.radius
            if cx + r < x or cx - r >= x + w or cy + r < y or cy - r >= y + h:
                continue
            mask = (xs - cx) ** 2 + (ys - cy) ** 2 <= r * r
            if not mask.any():
                continue
            cr, cg, cb = _entity_color(entity.id)
            region[..., 0] = np.where(mask, cr * glow, region[..., 0])
            region[..., 1] = np.where(mask, cg * glow, region[..., 1])
            region[..., 2] = np.where(mask, cb * glow, region[..., 2])

        return np.clip(region, 0, 255).astype(np.uint8)
