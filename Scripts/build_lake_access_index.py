"""Build compact entry-point reachability metrics for lake search.

The index intentionally measures trip complexity rather than geographic
distance: cumulative portage rods, number of portages, and lake-to-lake
transitions.  Each destination keeps its Pareto-optimal metric combinations so
the browser can apply several limits without claiming that one arbitrary
"shortest" path satisfies all of them.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import heapq
import json
import math
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHARD_TARGET_BYTES = 650_000


def _feature_properties(collection: dict[str, Any]):
    for feature in collection.get("features", []):
        yield feature.get("properties") or {}


def _entry_sort_key(entry: dict[str, str]):
    parts = re.split(r"(\d+)", entry["code"])
    return [int(part) if part.isdigit() else part.casefold() for part in parts]


def _dominates(left: tuple[float, int, int], right: tuple[float, int, int]):
    return all(a <= b for a, b in zip(left, right))


def _frontier_from(
    start: str,
    adjacency: dict[str, list[tuple[str, float, int, int]]],
    initial: tuple[float, int, int] = (0.0, 0, 0),
):
    frontiers: dict[str, list[tuple[float, int, int]]] = defaultdict(list)
    frontiers[start] = [initial]
    queue = [(*initial, start)]
    while queue:
        rods, portages, lakes_in, lake = heapq.heappop(queue)
        state = (rods, portages, lakes_in)
        if state not in frontiers[lake]:
            continue
        for neighbor, edge_rods, edge_portages, edge_lakes in adjacency.get(lake, []):
            candidate = (
                rods + edge_rods,
                portages + edge_portages,
                lakes_in + edge_lakes,
            )
            existing = frontiers[neighbor]
            if any(_dominates(item, candidate) for item in existing):
                continue
            frontiers[neighbor] = [
                item for item in existing if not _dominates(candidate, item)
            ]
            frontiers[neighbor].append(candidate)
            heapq.heappush(queue, (*candidate, neighbor))
    return frontiers


def build_access_index(portages, rivers, entry_points):
    adjacency: dict[str, list[tuple[str, float, int, int]]] = defaultdict(list)

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
            if left != right:
                self.parent[right] = left

    def lake_node(guid):
        return f"lake:{guid}"

    def id_key(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if math.isfinite(value) and float(value).is_integer():
                return str(int(value))
        return str(value)

    def add_edge(a, b, rods, portage_count, lakes_ab=1, lakes_ba=1):
        if not isinstance(a, str) or not isinstance(b, str) or not a or not b or a == b:
            return
        if (not isinstance(rods, (int, float)) or isinstance(rods, bool)
                or not math.isfinite(rods) or rods < 0):
            return
        adjacency[a].append((b, float(rods), portage_count, lakes_ab))
        adjacency[b].append((a, float(rods), portage_count, lakes_ba))

    river_rows = [row for row in _feature_properties(rivers) if row.get("routable")]
    river_components = Components()
    river_by_id = {}
    legacy_river_rows = []
    for row in river_rows:
        node_a, node_b = row.get("node_a"), row.get("node_b")
        if isinstance(node_a, str) and node_a and isinstance(node_b, str) and node_b:
            river_components.union(node_a, node_b)
        else:
            legacy_river_rows.append(row)
        river_by_id[id_key(row.get("river_id"))] = row

    for row in legacy_river_rows:
        guid_a, guid_b = row.get("unique_guid_a"), row.get("unique_guid_b")
        if isinstance(guid_a, str) and guid_a and isinstance(guid_b, str) and guid_b:
            add_edge(lake_node(guid_a), lake_node(guid_b), 0, 0)

    component_lakes = defaultdict(set)
    all_river_components = set()
    for row in river_rows:
        node = row.get("node_a") or row.get("node_b")
        if not isinstance(node, str) or not node:
            continue
        component = river_components.find(node)
        all_river_components.add(component)
        for guid in (row.get("unique_guid_a"), row.get("unique_guid_b")):
            if isinstance(guid, str) and guid:
                component_lakes[component].add(guid)

    water_nodes = {}
    for component in all_river_components:
        water = f"river:{component}"
        water_nodes[component] = water
        for guid in component_lakes[component]:
            # Leaving a lake for its river network does not add a lake.  A
            # different lake is counted only when the route enters it.
            add_edge(lake_node(guid), water, 0, 0, lakes_ab=0, lakes_ba=1)

    def river_anchor(river_id):
        row = river_by_id.get(id_key(river_id))
        if row is None:
            return None
        node = row.get("node_a") or row.get("node_b")
        if not isinstance(node, str) or not node:
            return None
        component = river_components.find(node)
        return water_nodes.get(component)

    def river_node_anchor(node_id):
        if (not isinstance(node_id, str) or not node_id
                or node_id not in river_components.parent):
            return None
        return water_nodes.get(river_components.find(node_id))

    def portage_anchor(row, side):
        routing_type = row.get(f"routing_type_{side}")
        if routing_type is None:  # compatibility with older generated layers
            guid = row.get(f"unique_guid_{side}")
            return lake_node(guid) if isinstance(guid, str) and guid else None
        if routing_type == "lake":
            guid = row.get(f"routing_lake_guid_{side}")
            return lake_node(guid) if isinstance(guid, str) and guid else None
        if routing_type == "river":
            return river_anchor(row.get(f"routing_river_id_{side}"))
        return None

    for row in _feature_properties(portages):
        anchor_a = portage_anchor(row, "a")
        anchor_b = portage_anchor(row, "b")
        add_edge(
            anchor_a,
            anchor_b,
            row.get("length_rods"),
            1,
            lakes_ab=1 if isinstance(anchor_b, str) and anchor_b.startswith("lake:") else 0,
            lakes_ba=1 if isinstance(anchor_a, str) and anchor_a.startswith("lake:") else 0,
        )

    entries_by_code = {}
    seeds_by_code = defaultdict(list)
    for row in _feature_properties(entry_points):
        code = row.get("code")
        if code is None:
            continue
        code = str(code)
        entries_by_code.setdefault(code, {
            "code": code,
            "name": f"{code} - {row.get('name') or f'Entry Point {code}'}",
            "location_count": int(row.get("location_count") or 1),
        })
        entries_by_code[code]["location_count"] = max(
            entries_by_code[code]["location_count"],
            int(row.get("location_count") or 1),
        )
        for attachment in row.get("attachments") or []:
            routing_type = attachment.get("routing_type")
            guid = attachment.get("lake_guid")
            if routing_type == "river":
                start = river_anchor(attachment.get("routing_river_id"))
                if start is None:
                    start = river_node_anchor(attachment.get("node_id"))
                # The first lake reached from an entry on a river is still
                # zero lakes in, matching a direct lake entry.
                initial_lakes = -1
            elif routing_type in {None, "lake"}:
                start = lake_node(guid) if isinstance(guid, str) and guid else None
                initial_lakes = 0
            else:
                start = None
                initial_lakes = 0
            rods = attachment.get("initial_rods", 0)
            portage_count = attachment.get("initial_portages", 0)
            if not isinstance(start, str) or not start:
                continue
            if (not isinstance(rods, (int, float)) or isinstance(rods, bool)
                    or not math.isfinite(rods) or rods < 0):
                continue
            if not isinstance(portage_count, int) or isinstance(portage_count, bool) or portage_count < 0:
                continue
            seeds_by_code[code].append(
                (start, (float(rods), portage_count, initial_lakes))
            )

    entries = [entry for code, entry in entries_by_code.items() if seeds_by_code.get(code)]
    entries.sort(key=_entry_sort_key)

    starts = {}
    for entry in entries:
        code = entry["code"]
        combined = defaultdict(list)
        for start, initial in seeds_by_code[code]:
            for destination_node, states in _frontier_from(start, adjacency, initial).items():
                if not destination_node.startswith("lake:"):
                    continue
                destination = destination_node[len("lake:"):]
                existing = combined[destination]
                for state in states:
                    if any(_dominates(item, state) for item in existing):
                        continue
                    existing[:] = [item for item in existing if not _dominates(state, item)]
                    existing.append(state)

        routes = {}
        for destination, states in combined.items():
            rounded = sorted({(round(rods, 1), portages, lakes_in)
                              for rods, portages, lakes_in in states})
            # Rounding can make two formerly distinct states dominate each other.
            rounded = [state for state in rounded
                       if not any(other != state and _dominates(other, state)
                                  for other in rounded)]
            routes[destination] = [list(state) for state in rounded]
        starts[code] = routes

    # An attachment to an isolated river component is still useful evidence
    # on the map, but it must not appear as a working entry filter until that
    # component has a verified path to at least one lake.
    entries = [entry for entry in entries if starts.get(entry["code"])]
    starts = {entry["code"]: starts[entry["code"]] for entry in entries}

    return {
        "schema_version": 3,
        "definitions": {
            "portage_rods": "Cumulative recorded portage length from the official entry location, in rods",
            "portages": "Number of portage segments",
            "lakes_in": "Lake-to-lake transitions after the entry attachment; its first routed water body is zero",
        },
        "entries": entries,
        "starts": starts,
    }


def write_access_index(result, output: Path, target_bytes=SHARD_TARGET_BYTES):
    """Write a small manifest plus independently fetchable entry-code shards."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    groups = []
    current = {}
    current_size = len('{"starts":{}}\n')
    for entry in result["entries"]:
        code = entry["code"]
        routes = result["starts"][code]
        encoded_size = len(json.dumps({code: routes}, separators=(",", ":")))
        if current and current_size + encoded_size > target_bytes:
            groups.append(current)
            current = {}
            current_size = len('{"starts":{}}\n')
        current[code] = routes
        current_size += encoded_size
    if current:
        groups.append(current)

    shard_paths = [
        output.with_name(f"{output.stem}_{index}{output.suffix}")
        for index in range(1, len(groups) + 1)
    ]
    for path, starts in zip(shard_paths, groups):
        path.write_text(json.dumps({"starts": starts}, sort_keys=True,
                                   separators=(",", ":")) + "\n")

    manifest = {key: value for key, value in result.items() if key != "starts"}
    manifest["shards"] = [path.name for path in shard_paths]
    output.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
    return [output, *shard_paths]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maps-dir", type=Path, default=ROOT / "maps")
    parser.add_argument("--stem", default="bwca_graph_map")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    maps_dir = args.maps_dir.resolve()

    def load(suffix):
        return json.loads((maps_dir / f"{args.stem}_{suffix}.json").read_text())

    result = build_access_index(load("portages"), load("rivers"), load("entry_points"))
    output = args.output or maps_dir / "lake_access_index.json"
    written = write_access_index(result, output)
    route_count = sum(len(routes) for routes in result["starts"].values())
    print(f"Wrote {output} and {len(written) - 1} shards: "
          f"{len(result['entries'])} entries, {len(result['starts'])} permit codes, "
          f"{route_count} reachable pairs")


if __name__ == "__main__":
    main()
