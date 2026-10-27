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
    adjacency: dict[str, list[tuple[str, float, int]]],
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
            guid = attachment.get("lake_guid")
            rods = attachment.get("initial_rods", 0)
            portage_count = attachment.get("initial_portages", 0)
            if not isinstance(guid, str) or not guid:
                continue
            if (not isinstance(rods, (int, float)) or isinstance(rods, bool)
                    or not math.isfinite(rods) or rods < 0):
                continue
            if not isinstance(portage_count, int) or isinstance(portage_count, bool) or portage_count < 0:
                continue
            seeds_by_code[code].append((guid, (float(rods), portage_count, 0)))

    entries = [entry for code, entry in entries_by_code.items() if seeds_by_code.get(code)]
    entries.sort(key=_entry_sort_key)

    starts = {}
    for entry in entries:
        code = entry["code"]
        combined = defaultdict(list)
        for start, initial in seeds_by_code[code]:
            for destination, states in _frontier_from(start, adjacency, initial).items():
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
