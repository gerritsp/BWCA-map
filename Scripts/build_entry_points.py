"""Attach official Forest Service water entries to the local routing graph.

An entry has two deliberately separate concepts:

* its GeoJSON point is the unchanged official public location; and
* its ``attachments`` property describes an inferred connection to a recorded
  lake, portage, or routable river.

This avoids moving an entry marker to the wilderness boundary or pretending a
nearest-lake spatial join is the real access location.  The browser draws any
non-trivial connector when the entry is used for routing.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import json
import math
from pathlib import Path
import re
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString, Point, mapping
from shapely.ops import nearest_points, substring


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "Data/entry_points/usfs_bwca_entry_points_2026.geojson"
ROUTABLE_ACCESS_TYPES = {"overnight", "overnight paddle", "day use motor"}
PORTAGE_FIRST_CODES = {"1", "A"}
PORTAGE_SIDE_OVERRIDES = {"7": "b", "19": "b", "70": "b"}
RIVER_SEARCH_LAKE_OVERRIDES = {"36": "Perent", "66": "Crocodile"}
SOURCE_CRS = "EPSG:26915"
WGS84 = "EPSG:4326"
ROD_TO_METERS = 5.0292


def _natural_key(value: str):
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", value)]


def _collection_gdf(collection: dict[str, Any]):
    features = collection.get("features", [])
    if not features:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=SOURCE_CRS)
    return gpd.GeoDataFrame.from_features(features, crs=WGS84).to_crs(SOURCE_CRS)


def _nearest(gdf, point):
    if gdf.empty:
        return None, math.inf
    distances = gdf.geometry.distance(point)
    index = distances.idxmin()
    return gdf.loc[index], float(distances.loc[index])


def _clean_name(value):
    words = re.findall(r"[a-z0-9]+", str(value or "").casefold())
    ignored = {"lake", "lakes", "river", "only", "from", "the", "and", "to", "lk", "lks"}
    return " ".join(word for word in words if word not in ignored)


def _name_score(left, right):
    a, b = _clean_name(left), _clean_name(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _json_value(value):
    if value is None:
        return None
    try:
        if bool(value != value):  # handles float and NumPy NaN without another dependency
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _named_lake(gdf, wanted, point):
    candidates = gdf[gdf["name"].map(lambda value: _name_score(wanted, value) >= 0.75)]
    if candidates.empty:
        return None
    row, _ = _nearest(candidates, point)
    return row


def _line_to_wgs84(line):
    return gpd.GeoSeries([line], crs=SOURCE_CRS).to_crs(WGS84).iloc[0]


def _confidence(offset_m):
    if offset_m <= 25:
        return "high"
    if offset_m <= 75:
        return "medium"
    return "review"


def _route_line(point, projected, segment):
    coords = [point.coords[0]]
    if point.distance(projected) > 0.05:
        coords.append(projected.coords[0])
    if segment.geom_type == "Point":
        segment_coords = [segment.coords[0]]
    else:
        segment_coords = list(segment.coords)
    for coord in segment_coords:
        if not coords or Point(coords[-1]).distance(Point(coord)) > 0.05:
            coords.append(coord)
    if len(coords) == 1:
        coords.append(coords[0])
    return LineString(coords)


def _lake_attachment(entry, point, lake, distance_m):
    target = point if lake.geometry.covers(point) else nearest_points(point, lake.geometry.boundary)[1]
    connector = LineString([point, target])
    return {
        "kind": "lake",
        "routing_type": "lake",
        "routing_river_id": None,
        "edge_kind": "paddle" if distance_m <= 25 else "approach",
        "lake_guid": lake.unique_guid,
        "lake_name": _json_value(lake.get("name")),
        "node_id": None,
        "route_coordinates": list(_line_to_wgs84(target).coords)[0]
        if target.geom_type == "Point" else None,
        "connector_geometry": mapping(_line_to_wgs84(connector)),
        "connector_distance_m": round(float(connector.length), 1),
        "initial_rods": 0.0,
        "initial_portages": 0,
        "network_offset_m": round(distance_m, 1),
        "confidence": _confidence(distance_m),
        "label": f"{_json_value(lake.get('name')) or 'unnamed lake'} shoreline",
    }


def _portage_attachment(entry, point, portage, distance_m, lake_names):
    line = portage.geometry
    location = line.project(point)
    projected = line.interpolate(location)
    endpoints = {
        "a": {
            "coord": Point(line.coords[0]),
            "routing_type": _json_value(portage.get("routing_type_a")) or "lake",
            "lake_guid": (
                _json_value(portage.get("routing_lake_guid_a"))
                if "routing_lake_guid_a" in portage else portage.unique_guid_a
            ),
            "river_id": _json_value(portage.get("routing_river_id_a")),
            "node_id": f"portage:{portage.portage_number}:a",
            "segment": substring(line, 0, location),
            "along_m": location,
        },
        "b": {
            "coord": Point(line.coords[-1]),
            "routing_type": _json_value(portage.get("routing_type_b")) or "lake",
            "lake_guid": (
                _json_value(portage.get("routing_lake_guid_b"))
                if "routing_lake_guid_b" in portage else portage.unique_guid_b
            ),
            "river_id": _json_value(portage.get("routing_river_id_b")),
            "node_id": f"portage:{portage.portage_number}:b",
            "segment": substring(line, location, line.length),
            "along_m": line.length - location,
        },
    }
    if endpoints["a"]["segment"].geom_type != "Point":
        endpoints["a"]["segment"] = LineString(list(endpoints["a"]["segment"].coords)[::-1])

    code = str(entry.entry_number)
    side = PORTAGE_SIDE_OVERRIDES.get(code)
    supported = {
        key for key, value in endpoints.items()
        if value["routing_type"] in {"lake", "river"}
        and (
            bool(value["lake_guid"])
            if value["routing_type"] == "lake"
            else value["river_id"] is not None
        )
    }
    if not supported:
        return None
    if side not in supported:
        side = None
    if (side is None and len(supported) > 1
            and endpoints["a"]["lake_guid"] != endpoints["b"]["lake_guid"]):
        scores = {
            key: _name_score(entry["name"], lake_names.get(value["lake_guid"]))
            for key, value in endpoints.items() if key in supported
        }
        best = max(scores, key=scores.get)
        other_scores = [score for key, score in scores.items() if key != best]
        if (scores[best] >= 0.55
                and (not other_scores or scores[best] - max(other_scores) >= 0.08)):
            side = best
    if side is None:
        side = max(supported, key=lambda key: endpoints[key]["along_m"])

    target = endpoints[side]
    route = _route_line(point, projected, target["segment"])
    fraction = target["along_m"] / line.length if line.length else 0.0
    recorded_rods = max(
        0.0, float(_json_value(portage.length_rods) or 0.0) * fraction
    )
    approach_rods = float(point.distance(projected)) / ROD_TO_METERS
    rods = recorded_rods + approach_rods
    lake_name = lake_names.get(target["lake_guid"])
    return {
        "kind": "portage",
        "routing_type": target["routing_type"],
        "routing_river_id": target["river_id"],
        "edge_kind": "portage",
        "lake_guid": target["lake_guid"],
        "lake_name": lake_name,
        "node_id": target["node_id"],
        "route_coordinates": list(_line_to_wgs84(target["coord"]).coords)[0],
        "connector_geometry": mapping(_line_to_wgs84(route)),
        "connector_distance_m": round(float(route.length), 1),
        "initial_rods": round(rods, 1),
        "initial_portages": 1 if rods > 0.5 else 0,
        "network_offset_m": round(distance_m, 1),
        "confidence": _confidence(distance_m),
        "label": f"Portage {portage.portage_number} to {lake_name or 'routing network'}",
    }


def _river_attachments(entry, point, river, distance_m, lake_names, fallback_lake=None):
    line = river.geometry
    location = line.project(point)
    projected = line.interpolate(location)
    sides = (
        ("a", river.node_a, river.unique_guid_a, substring(line, 0, location), location),
        ("b", river.node_b, river.unique_guid_b, substring(line, location, line.length), line.length - location),
    )
    attachments = []
    seen = set()
    for side, node_id, lake_guid, segment, along_m in sides:
        lake_guid = _json_value(lake_guid)
        if not lake_guid and fallback_lake is not None:
            lake_guid = fallback_lake.unique_guid
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        if side == "a" and segment.geom_type != "Point":
            segment = LineString(list(segment.coords)[::-1])
        target = Point(line.coords[0] if side == "a" else line.coords[-1])
        route = _route_line(point, projected, segment)
        attachments.append({
            "kind": "river",
            "routing_type": "river",
            "routing_river_id": _json_value(river.get("river_id")),
            "edge_kind": "river",
            "lake_guid": lake_guid,
            "lake_name": lake_names.get(lake_guid),
            "node_id": node_id,
            "route_coordinates": list(_line_to_wgs84(target).coords)[0],
            "connector_geometry": mapping(_line_to_wgs84(route)),
            "connector_distance_m": round(float(route.length), 1),
            "initial_rods": 0.0,
            "initial_portages": 0,
            "network_offset_m": round(distance_m, 1),
            "confidence": _confidence(distance_m),
            "label": f"{_json_value(river.get('name')) or 'recorded river'} ({side} connection)",
        })
    return attachments


def build_entry_points(lakes, portages, rivers, boundary, source_path=SOURCE_PATH):
    source = json.loads(Path(source_path).read_text(encoding="utf-8"))
    official = gpd.GeoDataFrame.from_features(source["features"], crs=WGS84)
    official = official[official.access_type.isin(ROUTABLE_ACCESS_TYPES)].to_crs(SOURCE_CRS)
    lake_gdf = _collection_gdf(lakes)
    portage_gdf = _collection_gdf(portages)
    river_gdf = _collection_gdf(rivers)
    if "routable" in river_gdf:
        river_gdf = river_gdf[river_gdf.routable.fillna(False)]
    _collection_gdf(boundary)  # validates that the legal boundary is readable
    lake_names = {row.unique_guid: _json_value(row.get("name"))
                  for _, row in lake_gdf.iterrows()}

    records = []
    for _, entry in official.iterrows():
        point = entry.geometry
        lake, lake_distance = _nearest(lake_gdf, point)
        portage, portage_distance = _nearest(portage_gdf, point)
        river, river_distance = _nearest(river_gdf, point)
        code = str(entry.entry_number)

        attachments = []
        method = None
        if code in PORTAGE_FIRST_CODES and portage is not None and portage_distance <= 150:
            method = "portage"
        elif entry.access_type == "overnight paddle":
            if portage is not None and portage_distance <= 100:
                method = "portage"
            elif lake is not None and lake_distance <= 50:
                method = "lake"
            elif river is not None and river_distance <= 150:
                method = "river"
            elif portage is not None and portage_distance <= 150:
                method = "portage"
            elif lake is not None and lake_distance <= 250:
                method = "lake"
        else:
            if lake is not None and lake_distance <= 250:
                method = "lake"
            elif portage is not None and portage_distance <= 150:
                method = "portage"

        # Some official landings lie outside a deficient or clipped local
        # shoreline.  A strong name match is safer than assigning a different,
        # geometrically closer water body; the long connector remains visible
        # and marked for review in the UI.
        if method is None and lake is not None and lake_distance <= 2500:
            if _name_score(entry["name"], lake.get("name")) >= 0.65:
                method = "lake"

        if method == "lake":
            attachments = [_lake_attachment(entry, point, lake, lake_distance)]
        elif method == "portage":
            attachment = _portage_attachment(
                entry, point, portage, portage_distance, lake_names
            )
            attachments = [attachment] if attachment else []
        elif method == "river":
            override_name = RIVER_SEARCH_LAKE_OVERRIDES.get(code)
            override_lake = _named_lake(lake_gdf, override_name, point) if override_name else None
            attachments = _river_attachments(
                entry, point, river, river_distance, lake_names, override_lake
            )
            if override_lake is not None:
                attachments.append(_lake_attachment(
                    entry,
                    point,
                    override_lake,
                    float(point.distance(override_lake.geometry)),
                ))

        # If a nearby portage ends outside the clipped local water layers, do
        # not revive its old arbitrary nearest-lake assignment.  A strong
        # official-name match to a lake or river is a safer visible fallback;
        # the long connector remains marked "review" by _confidence().
        if not attachments and lake is not None and lake_distance <= 2500:
            if _name_score(entry["name"], lake.get("name")) >= 0.65:
                method = "lake"
                attachments = [_lake_attachment(entry, point, lake, lake_distance)]
        if not attachments and river is not None and river_distance <= 1000:
            if _name_score(entry["name"], river.get("name")) >= 0.65:
                method = "river"
                attachments = _river_attachments(
                    entry, point, river, river_distance, lake_names
                )

        public_point = gpd.GeoSeries([point], crs=SOURCE_CRS).to_crs(WGS84).iloc[0]
        records.append({
            "code": code,
            "name": entry["name"],
            "access_type": entry.access_type,
            "official_revision": entry.rev_date,
            "official_source": source.get("source", {}).get("layer"),
            "routing_method": method or "unmatched",
            "routing_status": "connected" if attachments else "unmatched",
            "attachments": attachments,
            "geometry": public_point,
        })

    records.sort(key=lambda row: (_natural_key(row["code"]), row["geometry"].x, row["geometry"].y))
    totals = {}
    for record in records:
        totals[record["code"]] = totals.get(record["code"], 0) + 1
    seen = {}
    features = []
    for record in records:
        code = record.pop("code")
        geometry = record.pop("geometry")
        seen[code] = seen.get(code, 0) + 1
        record["code"] = code
        record["location_index"] = seen[code]
        record["location_count"] = totals[code]
        features.append({
            "type": "Feature",
            "id": f"{code}:{seen[code]}",
            "properties": record,
            "geometry": mapping(geometry),
        })
    return {
        "type": "FeatureCollection",
        "source": source.get("source"),
        "features": features,
    }
