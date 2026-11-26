"""Normalize generated numeric output across operating systems.

GEOS/PROJ calculations can differ by a few billionths between runner images.
Those differences are irrelevant to routing but make checked-in JSON hashes
unstable.  Coordinates are stored to six decimal degrees (roughly 0.1 m at
BWCA latitudes), while graph distances keep four decimal metres.
"""

from __future__ import annotations

from itertools import groupby
import math


COORDINATE_DECIMALS = 6
DISTANCE_DECIMALS = 4


def round_floats(value, decimals=COORDINATE_DECIMALS):
    """Return *value* with every finite float rounded recursively."""
    if isinstance(value, float):
        if not math.isfinite(value):
            return value
        rounded = round(value, decimals)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, list):
        return [round_floats(item, decimals) for item in value]
    if isinstance(value, tuple):
        return tuple(round_floats(item, decimals) for item in value)
    if isinstance(value, dict):
        return {key: round_floats(item, decimals) for key, item in value.items()}
    return value


def canonicalize_route_graph(graph):
    """Normalize coordinates and edge weights in a generated route graph."""
    for node in graph.get("nodes", []):
        if len(node) >= 3:
            node[2] = round_floats(node[2], COORDINATE_DECIMALS)
    for edge in graph.get("edges", []):
        if len(edge) >= 3 and isinstance(edge[2], float):
            edge[2] = round_floats(edge[2], DISTANCE_DECIMALS)
        if len(edge) >= 5:
            geometry = round_floats(edge[4], COORDINATE_DECIMALS)
            if isinstance(geometry, dict) and geometry.get("type") == "LineString":
                coords = geometry["coordinates"]
                if len(coords) >= 2:
                    distinct = [point for point, _ in groupby(coords)]
                    # A collapsed LineString still requires two positions.
                    geometry["coordinates"] = distinct if len(distinct) > 1 else distinct * 2
            edge[4] = geometry
    return graph
