"""
Resolves DNR LakeFinder fisheries data (Data/fisheries/*.parquet, all keyed by
dowlknum) onto this project's lakes (Data/processed/bwca_lakes.parquet, keyed
by unique_guid) and writes one JSON bundle per lake into maps/fisheries/.

Why not just join on dowlknum directly wherever fisheries data is needed:
dowlknum is NOT 1:1 with unique_guid in bwca_lakes.parquet. A single DOW lake
can correspond to multiple lake polygons here (e.g. Saganaga exists as three
separate unique_guid rows - the whole lake, the MN portion, and the Canada
portion - all sharing DOW number 16063300, because the DNR tracks fisheries
per whole lake, not per country-clipped fragment). That's a real, legitimate
many-to-one relationship, unlike the fw_id bug elsewhere in this project
(null/placeholder collisions) - the fix here is NOT to dedupe, it's to give
every unique_guid that shares a dowlknum the same fisheries bundle, so a
click on any portion of a DOW lake shows that lake's real fisheries data.

Verified against the actual project data: 499 DOW lakes, 25 of which map to
more than one unique_guid (same-lake splits like Saganaga/Moose), 0 fisheries
dowlknums with no match in bwca_lakes.parquet, 525 bundle files written.

Bundles are meant to be fetched by the browser only when a lake's detail
panel opens (not part of the eager-loaded lakes.json) - same lazy-fetch
pattern as the precomputed paddle-edge graph is fetched separately from the
base map data.

Run manually, like snap_portages.py - not yet part of APP.py's pipeline.
"""
import json
from pathlib import Path

import pandas as pd

LAKES_IN = "../../Data/processed/bwca_lakes.parquet"
FISHERIES_DIR = "../../Data/processed/fisheries"
BUNDLES_OUT_DIR = "../../maps/fisheries"

# Fisheries files always present. Add more filenames here as they become
# available (e.g. "dnr_surveys.parquet") - each is included automatically
# if the file exists, skipped (with a note) if it doesn't, so this script
# doesn't need to change again to pick them up later.
FISHERIES_FILES = {
    "lake_info": "dnr_lake_info.parquet",   # one row per DOW lake
    "fish_catches": "dnr_fish_catches.parquet",
    "fish_lengths": "dnr_fish_lengths.parquet",
    "water_clarity": "dnr_water_clarity.parquet",
    "surveys": "dnr_surveys.parquet",
    "accesses": "dnr_accesses.parquet",
    "plants": "dnr_plants.parquet",
}


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of JSON-safe dicts (NaN/NaT -> None)."""
    return df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")


def build_fisheries_bundles():
    fisheries_dir = Path(FISHERIES_DIR)
    bundles_out_dir = Path(BUNDLES_OUT_DIR)
    bundles_out_dir.mkdir(parents=True, exist_ok=True)

    # --- Load whatever fisheries files are actually present ---
    loaded = {}
    for key, filename in FISHERIES_FILES.items():
        path = fisheries_dir / filename
        if path.exists():
            loaded[key] = pd.read_parquet(path)
        else:
            print(f"Skipping {filename} (not found yet) - bundles will omit '{key}'")

    if "lake_info" not in loaded:
        raise SystemExit(f"{FISHERIES_FILES['lake_info']} is required and was not found.")

    lake_info = loaded["lake_info"]
    fisheries_dowlknums = set(lake_info["dowlknum"])

    # --- Build dowlknum -> [unique_guid, ...] lookup from bwca_lakes ---
    lakes = pd.read_parquet(LAKES_IN, columns=["dowlknum", "unique_guid", "pw_basin_name"])
    lakes = lakes[lakes["dowlknum"].notnull()]

    dowlknum_to_guids = {}
    for dowlknum, group in lakes.groupby("dowlknum"):
        dowlknum_to_guids[dowlknum] = list(
            zip(group["unique_guid"], group["pw_basin_name"])
        )

    unmatched = [d for d in fisheries_dowlknums if d not in dowlknum_to_guids]
    multi_guid = {
        d: guids for d, guids in dowlknum_to_guids.items()
        if d in fisheries_dowlknums and len(guids) > 1
    }

    # --- Group each fisheries table by dowlknum once, for fast per-lake lookup ---
    grouped = {}
    for key, df in loaded.items():
        if key == "lake_info":
            continue
        grouped[key] = {
            dowlknum: _records(sub_df.drop(columns=["dowlknum"]))
            for dowlknum, sub_df in df.groupby("dowlknum")
        }

    lake_info_by_dow = lake_info.set_index("dowlknum")

    # --- Write one bundle per dowlknum, to every unique_guid that shares it ---
    guids_with_data = []
    for dowlknum in fisheries_dowlknums:
        if dowlknum not in dowlknum_to_guids:
            continue  # already reported in `unmatched`

        info_row = lake_info_by_dow.loc[dowlknum]
        info_dict = info_row.where(pd.notnull(info_row), None).to_dict()

        bundle = {
            "dowlknum": dowlknum,
            "lake_info": info_dict,
        }
        for key in grouped:
            bundle[key] = grouped[key].get(dowlknum, [])

        for unique_guid, pw_basin_name in dowlknum_to_guids[dowlknum]:
            # Note which basin/polygon this bundle is attached to, since one
            # DOW lake's data may be shared across a handful of unique_guids
            # (see module docstring - e.g. Saganaga's MN/Canada/whole splits).
            bundle_for_guid = {**bundle, "matched_basin_name": pw_basin_name}
            out_path = bundles_out_dir / f"{unique_guid}.json"
            with open(out_path, "w") as f:
                json.dump(bundle_for_guid, f)
            guids_with_data.append(unique_guid)

    # Small index so APP.py can flag `has_fisheries_data` on the main lake
    # GeoJSON without re-deriving this join.
    with open(bundles_out_dir / "_index.json", "w") as f:
        json.dump(sorted(guids_with_data), f)

    print(f"Loaded fisheries tables: {sorted(loaded.keys())}")
    print(f"DOW lakes with fisheries data: {len(fisheries_dowlknums)}")
    print(f"DOW numbers matching >1 unique_guid: {len(multi_guid)} "
          f"(same lake split across multiple polygons - bundle written to all)")
    print(f"DOW numbers with NO match in bwca_lakes.parquet: {len(unmatched)}")
    if unmatched:
        print(f"  Unmatched dowlknums: {sorted(unmatched)}")
    print(f"Wrote {len(guids_with_data)} bundle files to {bundles_out_dir}/")
    print(f"Wrote index of {len(guids_with_data)} unique_guids to _index.json")
    print()
    print("Next step: in APP.py's lakes_geojson(), load _index.json once and add")
    print('  "has_fisheries_data": lake.unique_guid in fisheries_guids')
    print("to each lake's properties dict, so the map can show a badge/icon")
    print("without fetching a fisheries bundle for every lake up front.")


if __name__ == "__main__":
    build_fisheries_bundles()