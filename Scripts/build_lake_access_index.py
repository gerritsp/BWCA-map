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
    adjacency: dict[str, list[tuple[str, float, int]]],
):
    frontiers: dict[str, list[tuple[float, int, int]]] = defaultdict(list)
    frontiers[start] = [(0.0, 0, 0)]
    queue = [(0.0, 0, 0, start)]
    while queue:
        rods, portages, lakes_in, lake = heapq.heappop(queue)
        state = (rods, portages, lakes_in)
        if state not in frontiers[lake]:
            continue
        for neighbor, edge_rods, edge_portages in adjacency.get(lake, []):
            candidate = (
                rods + edge_rods,
                portages + edge_portages,
                lakes_in + 1,
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
    adjacency: dict[str, list[tuple[str, float, int]]] = defaultdict(list)

    def add_edge(a, b, rods, portage_count):
        if not isinstance(a, str) or not isinstance(b, str) or not a or not b or a == b:
            return
        if (not isinstance(rods, (int, float)) or isinstance(rods, bool)
                or not math.isfinite(rods) or rods < 0):
            return
        adjacency[a].append((b, float(rods), portage_count))
        adjacency[b].append((a, float(rods), portage_count))

    for row in _feature_properties(portages):
        add_edge(
            row.get("unique_guid_a"),
            row.get("unique_guid_b"),
            row.get("length_rods"),
            1,
        )
    for row in _feature_properties(rivers):
        if row.get("routable"):
            add_edge(row.get("unique_guid_a"), row.get("unique_guid_b"), 0, 0)

    entries = []
    for row in _feature_properties(entry_points):
        guid = row.get("unique_guid")
        code = row.get("code")
        if not isinstance(guid, str) or not guid or code is None:
            continue
        entries.append({
            "code": str(code),
            "name": str(row.get("name") or f"Entry Point {code}"),
            "lake_guid": guid,
        })
    entries.sort(key=_entry_sort_key)

    starts = {}
    for start in sorted({entry["lake_guid"] for entry in entries}):
        routes = {}
        for destination, states in _frontier_from(start, adjacency).items():
            rounded = sorted({(round(rods, 1), portages, lakes_in)
                              for rods, portages, lakes_in in states})
            # Rounding can make two formerly distinct states dominate each other.
            rounded = [state for state in rounded
                       if not any(other != state and _dominates(other, state)
                                  for other in rounded)]
            routes[destination] = [list(state) for state in rounded]
        starts[start] = routes

    return {
        "schema_version": 1,
        "definitions": {
            "portage_rods": "Cumulative portage length in rods",
            "portages": "Number of portage segments",
            "lakes_in": "Lake-to-lake transitions; the entry lake is zero",
        },
        "entries": entries,
        "starts": starts,
    }


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
    output.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    route_count = sum(len(routes) for routes in result["starts"].values())
    print(f"Wrote {output}: {len(result['entries'])} entries, "
          f"{len(result['starts'])} entry lakes, {route_count} reachable pairs")


if __name__ == "__main__":
    main()
