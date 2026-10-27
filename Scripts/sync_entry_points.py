"""Refresh the checked-in Forest Service BWCAW water-entry snapshot.

The source layer contains both water and hiking permits.  We retain the full
official response here; build_entry_points.py selects the water entries the
canoe-routing application can represent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
LAYER_URL = (
    "https://services1.arcgis.com/gGHDlz6USftL5Pau/ArcGIS/rest/services/"
    "R09_SNF_BWCAW_Entry_Points_2026/FeatureServer/0"
)
QUERY_URL = LAYER_URL + "/query?where=1%3D1&outFields=%2A&outSR=4326&f=geojson"
DEFAULT_OUTPUT = ROOT / "Data/entry_points/usfs_bwca_entry_points_2026.geojson"
EXPECTED_FIELDS = {"entry_number", "name", "access_type", "rev_date", "data_source"}


def _entry_key(feature):
    properties = feature["properties"]
    code = str(properties["entry_number"])
    parts = re.split(r"(\d+)", code)
    natural = [int(part) if part.isdigit() else part.casefold() for part in parts]
    lon, lat = feature["geometry"]["coordinates"]
    return natural, round(lon, 8), round(lat, 8)


def normalize(payload):
    if payload.get("type") != "FeatureCollection":
        raise ValueError("Forest Service response is not a FeatureCollection")
    cleaned = []
    for feature in payload.get("features", []):
        properties = feature.get("properties") or {}
        missing = EXPECTED_FIELDS - properties.keys()
        if missing:
            raise ValueError(f"Forest Service feature is missing fields: {sorted(missing)}")
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates")
        if geometry.get("type") != "Point" or not isinstance(coordinates, list) or len(coordinates) != 2:
            raise ValueError("Forest Service entry geometry is not a point")
        cleaned.append({
            "type": "Feature",
            "id": feature.get("id"),
            "properties": {
                "entry_number": str(properties["entry_number"]).strip(),
                "name": str(properties["name"]).strip(),
                "access_type": str(properties["access_type"]).strip().casefold(),
                "rev_date": properties["rev_date"],
                "data_source": properties["data_source"],
            },
            "geometry": {
                "type": "Point",
                "coordinates": [round(float(coordinates[0]), 12), round(float(coordinates[1]), 12)],
            },
        })
    if len(cleaned) < 80:
        raise ValueError(f"Forest Service layer unexpectedly has only {len(cleaned)} features")
    cleaned.sort(key=_entry_key)
    return {
        "type": "FeatureCollection",
        "source": {
            "agency": "USDA Forest Service, Superior National Forest",
            "layer": LAYER_URL,
            "query": QUERY_URL,
        },
        "features": cleaned,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    request = Request(QUERY_URL, headers={"User-Agent": "BWCA-map entry-point sync"})
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    normalized = normalize(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n")
    print(f"Wrote {args.output}: {len(normalized['features'])} official features")


if __name__ == "__main__":
    main()
