"""Neuro-symbolic & sparse video generation engine (proof of concept).

World state simulation (`scene`) is fully decoupled from raster rendering
(`renderer`): the scene graph only carries continuous parameters, and the
renderer turns state differences into localized pixel patches (P-frames)
over a persistent keyframe (I-frame).
"""
from engine.scene import Entity, LightSource, SceneGraph
from engine.renderer import FrameDelta, SparseRenderer
from engine.pipeline import VideoPipeline

__all__ = [
    "Entity",
    "LightSource",
    "SceneGraph",
    "FrameDelta",
    "SparseRenderer",
    "VideoPipeline",
]
