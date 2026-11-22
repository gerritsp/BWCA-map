"""Repair conservative, geometry-supported gaps in the static route graph.

The JavaScript precomputation deliberately avoids drawing paddle chords across
land.  A small shoreline sample can therefore leave valid landings on the same
polygon component disconnected, especially on large lakes with islands.  This
module adds only the missing minimum set of water-safe bridge edges, using a
constrained triangulation of the actual lake polygon.

Portage endpoints that are not within the browser's 25 m lake tolerance are
never attached to a kilometres-away "nearest" lake.  When APP.py identifies a
nearby mapped river, this module connects the endpoint to the exact projected
point on that river.  Remaining endpoints stay visibly marked for review.
"""

from __future__ import annotations

from collections import defaultdict
import heapq
import json
import math
import os
from pathlib import Path
import tempfile

import shapely
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import nearest_points, substring, unary_union
from shapely.strtree import STRtree
from pyproj import Transformer

try:
    from Scripts.canonicalize_output import canonicalize_route_graph
except ModuleNotFoundError:  # direct `python Scripts/repair_routing_graph.py`
    from canonicalize_output import canonicalize_route_graph  # type: ignore[no-redef]

try:
    from Scripts.river_topology import (
        RIVER_JUNCTION_TOLERANCE_M,
        find_river_junctions,
    )
except ModuleNotFoundError:  # direct `python Scripts/repair_routing_graph.py`
    from river_topology import (  # type: ignore[no-redef]
        RIVER_JUNCTION_TOLERANCE_M,
        find_river_junctions,
    )


WGS84 = "EPSG:4326"
SOURCE_CRS = "EPSG:26915"
LAKE_TOLERANCE_M = 25.0
NAV_SIMPLIFY_M = 15.0
REPAIR_VERSION = 2

TO_UTM = Transformer.from_crs(WGS84, SOURCE_CRS, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(SOURCE_CRS, WGS84, always_xy=True).transform


class UnionFind:
    def __init__(self):
        self.parent = {}
        self.rank = {}

    def add(self, value):
        if value not in self.parent:
            self.parent[value] = value
            self.rank[value] = 0

    def find(self, value):
        self.add(value)
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left, right):
        left = self.find(left)
        right = self.find(right)
        if left == right:
            return False
        if self.rank[left] < self.rank[right]:
            left, right = right, left
        self.parent[right] = left
        if self.rank[left] == self.rank[right]:
            self.rank[left] += 1
        return True


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_geojson(path):
    path = Path(path)
    data = _load(path)
    shards = data.get("shards") or []
    if not shards:
        return data
    features = []
    for shard in shards:
        if Path(shard).name != shard:
            raise ValueError(f"Invalid GeoJSON shard path: {shard}")
        features.extend(_load(path.parent / shard).get("features", []))
    expected = data.get("feature_count")
    if expected is not None and len(features) != expected:
        raise ValueError(
            f"Expected {expected} features in {path}, loaded {len(features)}"
        )
    return {"type": data.get("type", "FeatureCollection"), "features": features}


def _write_atomic(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as handle:
        json.dump(value, handle, separators=(",", ":"))
        temp_name = handle.name
    os.replace(temp_name, path)


def _to_utm(geometry):
    return shapely.transform(geometry, TO_UTM, interleaved=False)


def _to_wgs84(geometry):
    return shapely.transform(geometry, TO_WGS84, interleaved=False)


def _line(coords):
    cleaned = []
    for coord in coords:
        value = (float(coord[0]), float(coord[1]))
        if not cleaned or value != cleaned[-1]:
            cleaned.append(value)
    if len(cleaned) == 1:
        cleaned.append(cleaned[0])
    return LineString(cleaned)


def _id_key(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(value) and float(value).is_integer():
            return str(int(value))
    return str(value)


def _triangle_graph(polygon):
    nav_polygon = polygon.simplify(NAV_SIMPLIFY_M, preserve_topology=True)
    triangles = list(shapely.get_parts(
        shapely.constrained_delaunay_triangles(nav_polygon)
    ))
    triangles = [triangle for triangle in triangles if not triangle.is_empty]
    centers = [triangle.centroid for triangle in triangles]
    adjacency = [[] for _ in triangles]
    edge_owners = defaultdict(list)

    for index, triangle in enumerate(triangles):
        coords = list(triangle.exterior.coords)[:-1]
        for start, end in zip(coords, coords[1:] + coords[:1]):
            key = tuple(sorted((
                (round(start[0], 3), round(start[1], 3)),
                (round(end[0], 3), round(end[1], 3)),
            )))
            edge_owners[key].append(index)

    for owners in edge_owners.values():
        if len(owners) != 2:
            continue
        left, right = owners
        weight = centers[left].distance(centers[right])
        adjacency[left].append((right, weight))
        adjacency[right].append((left, weight))
    return nav_polygon, triangles, centers, adjacency


def _nearest_triangle(point, polygon, triangles, centers, tree):
    snapped = point if polygon.covers(point) else nearest_points(point, polygon)[1]
    matches = list(tree.query(snapped, predicate="intersects"))
    if matches:
        index = min(matches, key=lambda item: centers[int(item)].distance(snapped))
    else:
        index = tree.nearest(snapped)
    return int(index), snapped


def _shortest_paths(adjacency, source):
    distance = {source: 0.0}
    previous = {}
    queue = [(0.0, source)]
    while queue:
        current_distance, current = heapq.heappop(queue)
        if current_distance != distance.get(current):
            continue
        for neighbor, weight in adjacency[current]:
            candidate = current_distance + weight
            if candidate < distance.get(neighbor, math.inf):
                distance[neighbor] = candidate
                previous[neighbor] = current
                heapq.heappush(queue, (candidate, neighbor))
    return distance, previous


def _path(previous, source, target):
    if source == target:
        return [source]
    result = [target]
    while result[-1] != source:
        if result[-1] not in previous:
            return []
        result.append(previous[result[-1]])
    result.reverse()
    return result


def _smooth(coords, safe):
    if len(coords) <= 2:
        return coords
    result = [coords[0]]
    index = 0
    while index < len(coords) - 1:
        target = len(coords) - 1
        while target > index + 1:
            if safe.covers(LineString([coords[index], coords[target]])):
                break
            target -= 1
        result.append(coords[target])
        index = target
    return result


def _lake_paths(access_nodes, polygon):
    """Return true in-water paths for every reachable pair in one lake part.

    Straight, fully visible pairs avoid triangulation.  Pairs blocked by an
    island or peninsula share one constrained 15 m navigation mesh, while the
    final smoothed line is validated against the original full-resolution
    polygon (not the simplified navigation copy).
    """
    if len(access_nodes) < 2:
        return {}

    full_safe = polygon.buffer(0.5)
    landing_safe = polygon.buffer(LAKE_TOLERANCE_M + 0.5)
    shapely.prepare(full_safe)
    shapely.prepare(landing_safe)
    snapped = [
        point if polygon.covers(point) else nearest_points(point, polygon)[1]
        for _, point in access_nodes
    ]
    result = {}
    blocked = []
    for left in range(len(access_nodes)):
        for right in range(left + 1, len(access_nodes)):
            interior = _line([snapped[left].coords[0], snapped[right].coords[0]])
            if full_safe.covers(interior):
                route = _line([
                    access_nodes[left][1].coords[0],
                    snapped[left].coords[0],
                    snapped[right].coords[0],
                    access_nodes[right][1].coords[0],
                ])
                if landing_safe.covers(route):
                    result[(left, right)] = route
                    continue
            blocked.append((left, right))

    if not blocked:
        return result

    nav_polygon, triangles, centers, adjacency = _triangle_graph(polygon)
    if not triangles:
        return result
    tree = STRtree(triangles)
    located = [
        _nearest_triangle(point, nav_polygon, triangles, centers, tree)
        for point in snapped
    ]
    previous_by_source = {}
    for left in sorted({left for left, _ in blocked}):
        previous_by_source[left] = _shortest_paths(
            adjacency, located[left][0]
        )

    for left, right in blocked:
        distances, previous = previous_by_source[left]
        left_triangle, left_snap = located[left]
        right_triangle, right_snap = located[right]
        if right_triangle not in distances:
            continue
        triangle_path = _path(previous, left_triangle, right_triangle)
        inside_coords = [left_snap.coords[0]]
        inside_coords.extend(centers[index].coords[0] for index in triangle_path)
        inside_coords.append(right_snap.coords[0])
        inside_coords = _smooth(inside_coords, full_safe)
        route = _line([
            access_nodes[left][1].coords[0],
            *inside_coords,
            access_nodes[right][1].coords[0],
        ])
        if landing_safe.covers(route):
            result[(left, right)] = route
    return result


def _burn_checker(fires):
    geometries = [
        _to_utm(shape(feature["geometry"]))
        for feature in fires.get("features", [])
        if feature.get("geometry")
    ]
    if not geometries:
        return lambda geometry: False
    fire_union = unary_union(geometries)
    return lambda geometry: bool(geometry.intersects(fire_union))


def repair_routing_graph(stem_path):
    stem = Path(stem_path)
    graph_path = stem.with_name(stem.name + "_paddle_edges.json")
    graph = _load(graph_path)
    prior_repair = graph.get("topology_repair") or {}
    if prior_repair.get("repair_version") == REPAIR_VERSION:
        print(f"Routing graph already repaired: {graph_path}")
        return prior_repair
    lakes = _load_geojson(stem.with_name(stem.name + "_lakes.json"))
    portages = _load(stem.with_name(stem.name + "_portages.json"))
    rivers = _load(stem.with_name(stem.name + "_rivers.json"))
    fires = _load(stem.with_name(stem.name + "_fires.json"))

    nodes = {node[0]: node for node in graph.get("nodes", [])}
    edges = graph.setdefault("edges", [])
    edge_keys = {
        (tuple(sorted((edge[0], edge[1]))), edge[3])
        for edge in edges
        if len(edge) >= 4
    }
    union = UnionFind()
    in_lake = UnionFind()
    for node_id in nodes:
        union.add(node_id)
        in_lake.add(node_id)
    for edge in edges:
        union.union(edge[0], edge[1])
        if len(edge) >= 4 and edge[3] == "paddle":
            left_lake = nodes.get(edge[0], [None, None])[1]
            right_lake = nodes.get(edge[1], [None, None])[1]
            if left_lake and left_lake == right_lake:
                in_lake.union(edge[0], edge[1])

    crosses_burn = _burn_checker(fires)

    def add_node(node_id, lake_id, point):
        if node_id in nodes:
            return
        coord = list(_to_wgs84(point).coords)[0]
        node = [node_id, lake_id, [coord[0], coord[1]]]
        graph["nodes"].append(node)
        nodes[node_id] = node
        union.add(node_id)
        in_lake.add(node_id)

    def add_edge(left, right, geometry, kind):
        if left not in nodes or right not in nodes:
            return False
        key = (tuple(sorted((left, right))), kind)
        if key in edge_keys:
            union.union(left, right)
            return False
        geometry = _line(geometry.coords)
        serialized_geometry = (
            None
            if kind == "paddle" and len(geometry.coords) == 2
            else mapping(_to_wgs84(geometry))
        )
        edges.append([
            left,
            right,
            float(geometry.length),
            kind,
            serialized_geometry,
            crosses_burn(geometry) if kind in {"portage", "approach"} else False,
        ])
        edge_keys.add(key)
        union.union(left, right)
        if kind == "paddle" and nodes[left][1] and nodes[left][1] == nodes[right][1]:
            in_lake.union(left, right)
        return True

    river_by_id = {
        _id_key(feature.get("properties", {}).get("river_id")): feature
        for feature in rivers.get("features", [])
    }
    river_attachments = 0
    for feature in portages.get("features", []):
        properties = feature.get("properties") or {}
        number = properties.get("portage_number")
        for side, suffix in (("a", "a"), ("b", "b")):
            if properties.get(f"routing_type_{side}") != "river":
                continue
            river = river_by_id.get(_id_key(properties.get(f"routing_river_id_{side}")))
            portage_node = f"portage:{number}:{suffix}"
            if river is None or portage_node not in nodes:
                continue

            line = _to_utm(shape(river["geometry"]))
            point = _to_utm(Point(nodes[portage_node][2]))
            location = line.project(point)
            projected = line.interpolate(location)
            river_properties = river.get("properties") or {}
            node_a = river_properties.get("node_a")
            node_b = river_properties.get("node_b")

            if location <= 0.05:
                add_edge(portage_node, node_a, _line([point.coords[0], line.coords[0]]), "approach")
            elif line.length - location <= 0.05:
                add_edge(portage_node, node_b, _line([point.coords[0], line.coords[-1]]), "approach")
            else:
                snap_node = f"portage-river:{number}:{suffix}"
                add_node(snap_node, None, projected)
                add_edge(portage_node, snap_node,
                         _line([point.coords[0], projected.coords[0]]), "approach")
                first = substring(line, 0, location)
                second = substring(line, location, line.length)
                if first.geom_type == "Point":
                    first = _line([first.coords[0], first.coords[0]])
                if second.geom_type == "Point":
                    second = _line([second.coords[0], second.coords[0]])
                add_edge(snap_node, node_a, first, "river")
                add_edge(snap_node, node_b, second, "river")
            river_attachments += 1

    river_rows = []
    for feature in rivers.get("features", []):
        properties = feature.get("properties") or {}
        if not properties.get("routable") or not feature.get("geometry"):
            continue
        river_rows.append({
            "river_id": _id_key(properties.get("river_id")),
            "node_a": properties.get("node_a"),
            "node_b": properties.get("node_b"),
            "geometry": _to_utm(shape(feature["geometry"])),
        })

    river_junctions = 0
    for junction in find_river_junctions(river_rows):
        source_node = junction["source_node"]
        node_a = junction["target_node_a"]
        node_b = junction["target_node_b"]
        if source_node not in nodes or node_a not in nodes or node_b not in nodes:
            continue
        line = junction["target_line"]
        point = junction["point"]
        location = line.project(point)
        projected = line.interpolate(location)
        if location <= 0.05:
            add_edge(source_node, node_a,
                     _line([point.coords[0], line.coords[0]]), "river")
        elif line.length - location <= 0.05:
            add_edge(source_node, node_b,
                     _line([point.coords[0], line.coords[-1]]), "river")
        else:
            snap_node = (
                f"river-junction:{junction['source_id']}:"
                f"{junction['source_side']}:{junction['target_id']}"
            )
            add_node(snap_node, None, projected)
            add_edge(source_node, snap_node,
                     _line([point.coords[0], projected.coords[0]]), "river")
            first = substring(line, 0, location)
            second = substring(line, location, line.length)
            if first.geom_type == "Point":
                first = _line([first.coords[0], first.coords[0]])
            if second.geom_type == "Point":
                second = _line([second.coords[0], second.coords[0]])
            add_edge(snap_node, node_a, first, "river")
            add_edge(snap_node, node_b, second, "river")
        river_junctions += 1

    lake_rows = []
    for feature in lakes.get("features", []):
        if not feature.get("geometry"):
            continue
        lake_rows.append({
            "lake_id": feature.get("properties", {}).get("unique_guid"),
            "geometry": _to_utm(shape(feature["geometry"])),
        })
    lake_geometries = {row["lake_id"]: row["geometry"] for row in lake_rows}

    groups = defaultdict(list)
    for node_id, lake_id, coord in nodes.values():
        if not lake_id or node_id.startswith("vertex:") or lake_id not in lake_geometries:
            continue
        point = _to_utm(Point(coord))
        lake = lake_geometries[lake_id]
        parts = list(lake.geoms) if lake.geom_type == "MultiPolygon" else [lake]
        distances = [point.distance(part) for part in parts]
        part_index = min(range(len(parts)), key=distances.__getitem__)
        if distances[part_index] <= LAKE_TOLERANCE_M + 0.01:
            groups[(lake_id, part_index)].append((node_id, point))

    # Add one exact water route for every pair of graph access nodes on a lake
    # part.  A minimum spanning tree alone is connected but can send a 2 km
    # crossing through dozens of other lakes.  We still record the size of the
    # minimum connecting subset as a topology metric.
    lake_pair_edges = 0
    lake_bridges = 0
    repaired_parts = 0
    for (lake_id, part_index), access_nodes in groups.items():
        if len(access_nodes) < 2:
            continue
        lake = lake_geometries[lake_id]
        part = list(lake.geoms)[part_index] if lake.geom_type == "MultiPolygon" else lake
        paths = _lake_paths(access_nodes, part)
        lake_pair_edges += len(paths)
        candidate_edges = [
            (route.length, left, right, route)
            for (left, right), route in paths.items()
        ]

        component_union = UnionFind()
        for index in range(len(access_nodes)):
            component_union.add(index)
        selected = 0
        for _, left, right, route in sorted(candidate_edges):
            if component_union.union(left, right):
                selected += 1
        if selected != len(access_nodes) - 1:
            continue
        lake_bridges += selected
        repaired_parts += 1

        for (left, right), route in paths.items():
            add_edge(access_nodes[left][0], access_nodes[right][0], route, "paddle")

    graph["topology_repair"] = {
        "lake_pair_edges": lake_pair_edges,
        "lake_bridge_edges": lake_bridges,
        "repaired_lake_parts": repaired_parts,
        "river_portage_attachments": river_attachments,
        "river_junction_attachments": river_junctions,
        "river_junction_tolerance_m": RIVER_JUNCTION_TOLERANCE_M,
        "lake_tolerance_m": LAKE_TOLERANCE_M,
        "repair_version": REPAIR_VERSION,
    }
    canonicalize_route_graph(graph)
    _write_atomic(graph_path, graph)
    print(
        f"Repaired {graph_path}: {river_attachments} portage/river attachments, "
        f"{river_junctions} river junctions, {lake_pair_edges} lake pair routes, "
        f"{lake_bridges} lake bridge edges "
        f"across {repaired_parts} polygon parts"
    )
    return graph["topology_repair"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stem", type=Path)
    args = parser.parse_args()
    repair_routing_graph(args.stem)
