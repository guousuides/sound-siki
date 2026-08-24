"""Registry of available demons."""
from __future__ import annotations

from .base import Demon
from .cicada import CicadaDemon
from .train import TrainDemon

REGISTRY = {d.name: d for d in (TrainDemon, CicadaDemon)}

__all__ = ["Demon", "REGISTRY", "TrainDemon", "CicadaDemon"]
