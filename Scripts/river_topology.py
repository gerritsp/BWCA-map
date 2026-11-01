"""Identify exact endpoint-to-interior junctions in mapped river lines."""

from __future__ import annotations

from collections import defaultdict

from shapely.geometry import Point
from shapely.strtree import STRtree


RIVER_JUNCTION_TOLERANCE_M = 0.1


class Components:
    def __init__(self):
        self.parent = {}

    def find(self, value):
        self.parent.setdefault(value, value)
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, left, right):
        left, right = self.find(left), self.find(right)
        if left == right:
            return False
        self.parent[right] = left
        return True


def find_river_junctions(rows, tolerance=RIVER_JUNCTION_TOLERANCE_M):
    """Yield endpoints that land on a different river line.

    ``rows`` must provide ``geometry``, ``node_a``, ``node_b`` and
    ``river_id`` keys. Geometries must use a projected CRS whose units are
    meters. Multiple hits are retained because more than two segments may
    meet at one confluence.
    """
    if not rows:
        return
    raw_components = Components()
    for row in rows:
        raw_components.union(row["node_a"], row["node_b"])
    tree = STRtree([row["geometry"] for row in rows])
    for source_index, row in enumerate(rows):
        line = row["geometry"]
        endpoints = (
            ("a", row["node_a"], Point(line.coords[0])),
            ("b", row["node_b"], Point(line.coords[-1])),
        )
        for side, node_id, point in endpoints:
            source_component = raw_components.find(node_id)
            best_by_target_component = {}
            matches = tree.query(
                point, predicate="dwithin", distance=tolerance
            )
            for target_value in matches:
                target_index = int(target_value)
                if target_index == source_index:
                    continue
                target = rows[target_index]
                target_component = raw_components.find(target["node_a"])
                if target_component == source_component:
                    continue
                distance = float(point.distance(target["geometry"]))
                if distance > tolerance:
                    continue
                candidate = {
                    "source_index": source_index,
                    "source_id": row["river_id"],
                    "source_side": side,
                    "source_node": node_id,
                    "point": point,
                    "target_index": target_index,
                    "target_id": target["river_id"],
                    "target_node_a": target["node_a"],
                    "target_node_b": target["node_b"],
                    "target_line": target["geometry"],
                    "distance": distance,
                }
                previous = best_by_target_component.get(target_component)
                sort_key = (distance, str(target["river_id"]))
                if previous is None or sort_key < previous[0]:
                    best_by_target_component[target_component] = (sort_key, candidate)
            for _, candidate in sorted(
                best_by_target_component.values(), key=lambda item: item[0]
            ):
                yield candidate


def river_component_labels(rows, tolerance=RIVER_JUNCTION_TOLERANCE_M):
    """Return a stable component label for every river ID."""
    components = Components()
    for row in rows:
        components.union(row["node_a"], row["node_b"])
    for junction in find_river_junctions(rows, tolerance):
        components.union(junction["source_node"], junction["target_node_a"])

    groups = defaultdict(list)
    for node_id in components.parent:
        groups[components.find(node_id)].append(node_id)
    labels = {
        root: min(nodes)
        for root, nodes in groups.items()
    }
    return {
        row["river_id"]: labels[components.find(row["node_a"])]
        for row in rows
    }
