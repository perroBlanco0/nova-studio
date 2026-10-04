import gc
import sys
import tracemalloc
import numpy as np
import pytest

from engine.scene import SceneGraph, Entity, LightSource
from engine.renderer import SparseRenderer, FrameDelta
from engine.pipeline import VideoPipeline


def test_scene_state_payload_under_threshold():
    """Validates that intermediate state avoids dense tensors and stays under 10 KB."""
    scene = SceneGraph()
    scene.add_entity(Entity(id="actor_01", pos=(120.5, 340.2, 10.0), vel=(1.5, 0.0, 0.0), radius=15.0))
    scene.add_entity(Entity(id="actor_02", pos=(50.0, 80.0, 0.0), vel=(0.0, -0.5, 0.0), radius=8.0))
    scene.set_light(LightSource(pos=(300.0, 0.0, 50.0), intensity=0.85))

    serialized_bytes = scene.serialize()
    size_in_bytes = len(serialized_bytes)

    assert size_in_bytes < 10 * 1024, f"State payload exceeds 10 KB: {size_in_bytes} bytes"
    assert not hasattr(scene, "frame_buffer"), "Scene state must not store pixel buffers"


def test_state_reproducibility_deterministic():
    """Ensures deterministic state transition across runs."""
    scene_a = SceneGraph.from_seed(seed=42)
    scene_b = SceneGraph.from_seed(seed=42)

    scene_a.step(delta_time=1 / 30)
    scene_b.step(delta_time=1 / 30)

    assert scene_a.serialize() == scene_b.serialize(), "Simulation step is non-deterministic"


def test_static_scene_produces_zero_delta_computation():
    """Ensures stationary scenes consume 0 pixel computation cycles."""
    renderer = SparseRenderer(width=1280, height=720)
    scene = SceneGraph()
    scene.add_entity(Entity(id="static_box", pos=(200, 200, 0), vel=(0, 0, 0), radius=20))

    i_frame = renderer.render_keyframe(scene)
    assert i_frame.shape == (720, 1280, 3)

    scene.step(delta_time=1 / 30)
    delta: FrameDelta = renderer.compute_delta(scene)

    assert delta.modified_pixel_count == 0, "Static scenes must not compute pixel deltas"
    assert delta.bounding_boxes == [], "Active bounding boxes must be empty for stationary states"


def test_sparse_bounding_box_locality():
    """Validates that delta rasterization is localized and preserves unaffected regions."""
    width, height = 1920, 1080
    renderer = SparseRenderer(width=width, height=height)
    scene = SceneGraph()

    entity = Entity(id="ball", pos=(100, 100, 0), vel=(5, 0, 0), radius=10)
    scene.add_entity(entity)

    initial_frame = renderer.render_keyframe(scene).copy()
    scene.step(delta_time=1 / 30)
    delta: FrameDelta = renderer.compute_delta(scene)

    total_pixels = width * height
    assert delta.modified_pixel_count < (total_pixels * 0.05), "Delta modified an excessively large canvas area"

    renderer.apply_delta_in_place(delta)
    composite_frame = renderer.get_current_frame()

    # Verify pixels strictly outside dynamic bounding boxes remain bit-identical
    mask_untouched = np.ones((height, width), dtype=bool)
    for bbox in delta.bounding_boxes:
        x, y, w, h = bbox
        mask_untouched[max(0, y):min(height, y+h), max(0, x):min(width, x+w)] = False

    assert np.array_equal(composite_frame[mask_untouched], initial_frame[mask_untouched]), (
        "Static canvas areas were mutated or corrupted during delta application"
    )


def test_pipeline_zero_memory_leak_over_frames():
    """Ensures flat O(1) memory consumption over extended frame generation."""
    pipeline = VideoPipeline(width=1280, height=720, fps=30)
    scene = SceneGraph()
    scene.add_entity(Entity(id="dynamic_actor", pos=(50, 50, 0), vel=(2, 2, 0), radius=15))

    pipeline.generate_frame(scene)
    gc.collect()

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    for _ in range(300):
        scene.step(delta_time=1 / 30)
        _ = pipeline.generate_frame(scene)

    gc.collect()
    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snapshot_after.compare_to(snapshot_before, 'lineno')
    total_memory_diff_kb = sum(stat.size_diff for stat in stats) / 1024

    MAX_ALLOWED_GROWTH_KB = 5 * 1024  # Max 5 MB residual fluctuation allowed
    assert total_memory_diff_kb < MAX_ALLOWED_GROWTH_KB, (
        f"Memory leak detected: allocated size grew by {total_memory_diff_kb:.2f} KB across 300 frames"
    )


def test_buffer_reuse_without_reallocation():
    """Verifies that the renderer reuses internal buffers without new heap allocations per frame."""
    renderer = SparseRenderer(width=640, height=480)
    scene = SceneGraph()
    scene.add_entity(Entity(id="obj", pos=(20, 20, 0), vel=(1, 0, 0), radius=5))

    renderer.render_keyframe(scene)
    initial_buffer_address = renderer.frame_buffer_ptr()

    for _ in range(10):
        scene.step(delta_time=1 / 30)
        delta = renderer.compute_delta(scene)
        renderer.apply_delta_in_place(delta)

        current_buffer_address = renderer.frame_buffer_ptr()
        assert current_buffer_address == initial_buffer_address, (
            "Renderer reallocated the main frame buffer instead of mutating in-place"
        )
