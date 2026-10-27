"""Built-in fallback for the OSC 2.1 standard library.

The ASAM `types.osc` / `domain.osc` files cannot be redistributed with this
repository. This module provides the subset needed by the development
scenarios so the middle-end is usable offline. When the licensed ASAM files
are available, pass them to `osc2c check --stdlib ...`; user declarations are
resolved on top of these builtins.
"""

from __future__ import annotations

import math

from osc2c.semantics.types import Dimension, dimension

STDTYPES_NS = "stdtypes"
STANDARD_NS = "std"

PHYSICAL_TYPES: dict[str, Dimension] = {
    "length": dimension(m=1),
    "distance": dimension(m=1),
    "speed": dimension(m=1, s=-1),
    "acceleration": dimension(m=1, s=-2),
    "time": dimension(s=1),
    "angle": dimension(rad=1),
    "mass": dimension(kg=1),
    "temperature": dimension(K=1),
    "electric_current": dimension(A=1),
    "amount_of_substance": dimension(mol=1),
    "luminous_intensity": dimension(cd=1),
    "frequency": dimension(s=-1),
    "force": dimension(kg=1, m=1, s=-2),
    "energy": dimension(kg=1, m=2, s=-2),
}

# name -> (physical type, factor to SI, offset)
UNITS: dict[str, tuple[str, float, float]] = {
    "m": ("length", 1.0, 0.0),
    "km": ("length", 1000.0, 0.0),
    "cm": ("length", 0.01, 0.0),
    "mm": ("length", 0.001, 0.0),
    "s": ("time", 1.0, 0.0),
    "ms": ("time", 0.001, 0.0),
    "min": ("time", 60.0, 0.0),
    "h": ("time", 3600.0, 0.0),
    "rad": ("angle", 1.0, 0.0),
    "deg": ("angle", math.pi / 180.0, 0.0),
    "mps": ("speed", 1.0, 0.0),
    "kph": ("speed", 1000.0 / 3600.0, 0.0),
    "mph": ("speed", 0.44704, 0.0),
    "kg": ("mass", 1.0, 0.0),
    "g": ("mass", 0.001, 0.0),
    "K": ("temperature", 1.0, 0.0),
    "A": ("electric_current", 1.0, 0.0),
    "mol": ("amount_of_substance", 1.0, 0.0),
    "cd": ("luminous_intensity", 1.0, 0.0),
}

ENUMS: dict[str, list[str]] = {
    "direction": ["start", "end"],
    "side": ["left", "right"],
}

# `fields` values and `methods` parameter/result types refer to builtin names.
# All composite shells are created before their members are linked, so the
# mutual references (position <-> vehicle) resolve cleanly.
COMPOSITES: list[dict] = [
    {
        "name": "traffic_participant",
        "kind": "actor",
        "fields": {"name": "string", "position": "position"},
        "methods": {},
    },
    {
        "name": "vehicle",
        "kind": "actor",
        "base": "traffic_participant",
        "fields": {"model": "string", "speed": "speed"},
        "methods": {
            "drive": {"params": [], "result": None},
            "assign_position": {"params": [], "result": None},
        },
    },
    {
        "name": "pedestrian",
        "kind": "actor",
        "base": "traffic_participant",
        "fields": {"model": "string", "speed": "speed"},
        "methods": {"walk": {"params": [], "result": None}},
    },
    {
        "name": "environment",
        "kind": "actor",
        "base": "traffic_participant",
        "fields": {},
        "methods": {
            "assign_celestial_position": {
                "params": [("azimuth", "angle", False), ("elevation", "angle", False)],
                "result": None,
            }
        },
    },
    {
        "name": "position",
        "kind": "struct",
        "fields": {"x": "length", "y": "length", "z": "length"},
        "methods": {
            "ahead_of": {
                "params": [("other", "traffic_participant", False)],
                "result": "length",
            }
        },
    },
]

# name -> (target actor, [(param, type, has_default), ...])
MODIFIERS: dict[str, tuple[str | None, list[tuple[str, str, bool]]]] = {
    "speed": (
        "vehicle",
        [("speed", "speed", False), ("at", "direction", True)],
    ),
    "lane": (
        "vehicle",
        [
            ("lane", "int", True),
            ("side", "side", True),
            ("side_of", "traffic_participant", True),
            ("at", "direction", True),
        ],
    ),
    "position": (
        None,
        [
            ("x", "length", True),
            ("y", "length", True),
            ("z", "length", True),
            ("h", "angle", True),
            ("distance", "length", True),
            ("behind", "traffic_participant", True),
            ("ahead_of", "traffic_participant", True),
            ("at", "direction", True),
        ],
    ),
}

# Every actor carries these fields even when a user actor does not inherit a
# standard base (e.g. `actor vehicle:` in the grammar tour).
IMPLICIT_ACTOR_FIELDS: dict[str, str] = {
    "name": "string",
    "position": "position",
}
