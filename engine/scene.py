"""Symbolic scene representation.

The scene graph is strictly parametric: entities are positions, velocities,
radii and a bounding shape; lighting is a position plus intensity. No pixel
buffers, arrays or tensors ever live here, so a serialized frame of state
stays tiny (well under 10 KB).

Simulation is deterministic: the same starting state plus the same
`delta_time` always produces the same next state.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass

MAX_PAYLOAD_BYTES = 10 * 1024


@dataclass
class Entity:
    id: str
    pos: tuple[float, float, float]
    vel: tuple[float, float, float]
    radius: float

    def aabb(self) -> tuple[int, int, int, int]:
        """Integer bounding box (x0, y0, x1, y1) of the entity's disc."""
        x, y, _z = self.pos
        r = self.radius
        return (
            math.floor(x - r),
            math.floor(y - r),
            math.ceil(x + r),
            math.ceil(y + r),
        )

    def state_key(self) -> tuple:
        return (self.pos, self.vel, self.radius)


@dataclass
class LightSource:
    pos: tuple[float, float, float]
    intensity: float

    def state_key(self) -> tuple:
        return (self.pos, self.intensity)


class SceneGraph:
    """Flat parametric world state. Steps by simple Euler integration."""

    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.light: LightSource | None = None

    @classmethod
    def from_seed(cls, seed: int, n_entities: int = 8) -> "SceneGraph":
        """Build a reproducible scene from a seed."""
        rng = random.Random(seed)
        scene = cls()
        for i in range(n_entities):
            scene.add_entity(Entity(
                id=f"entity_{i:02d}",
                pos=(
                    rng.uniform(0.0, 640.0),
                    rng.uniform(0.0, 360.0),
                    rng.uniform(0.0, 50.0),
                ),
                vel=(rng.uniform(-4.0, 4.0), rng.uniform(-4.0, 4.0), 0.0),
                radius=rng.uniform(4.0, 18.0),
            ))
        scene.set_light(LightSource(
            pos=(rng.uniform(0.0, 640.0), rng.uniform(0.0, 360.0), 50.0),
            intensity=rng.uniform(0.5, 1.0),
        ))
        return scene

    def add_entity(self, entity: Entity) -> None:
        self.entities[entity.id] = entity

    def remove_entity(self, entity_id: str) -> None:
        self.entities.pop(entity_id, None)

    def set_light(self, light: LightSource) -> None:
        self.light = light

    def step(self, delta_time: float) -> None:
        """Advance the world by `delta_time` seconds (deterministic)."""
        for entity in self.entities.values():
            x, y, z = entity.pos
            vx, vy, vz = entity.vel
            entity.pos = (
                x + vx * delta_time,
                y + vy * delta_time,
                z + vz * delta_time,
            )

    def serialize(self) -> bytes:
        """Serialize the whole world state to a compact byte payload."""
        payload = {
            "entities": [
                {
                    "id": e.id,
                    "pos": [round(c, 9) for c in e.pos],
                    "vel": [round(c, 9) for c in e.vel],
                    "radius": e.radius,
                }
                for e in sorted(self.entities.values(), key=lambda e: e.id)
            ],
            "light": None if self.light is None else {
                "pos": [round(c, 9) for c in self.light.pos],
                "intensity": self.light.intensity,
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
