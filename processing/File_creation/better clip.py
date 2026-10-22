"""
Extends portage endpoint matching to fall back to a river when no lake is
close enough - today portages_final.parquet only ever matches lakes
(start_unid/end_unid), so a portage whose true endpoint is on a river has
no correct match at all.

Logic per endpoint (start and end handled independently):
  1. Lake match already exists on the row (start_unid/start_distance_m from
     the normal pipeline). If that distance is within LAKE_THRESHOLD_M, keep
     it - lake is always preferred when it's actually close enough.
  2. Otherwise, look for the nearest river within RIVER_THRESHOLD_M.
  3. Otherwise, leave it unmatched (same as today) - this is NOT the place
     to widen thresholds just to force a match; an endpoint that's far from
     both a lake and a river needs the boundary-clip-style investigation the
     ~5 known bad portages already get, not a bigger number here.

A single threshold per water type is used rather than a tiered "check 25m,
then 50m" river search - functionally identical, since anything within 25m
is also found by a single max_distance=50 search. The actual match distance
is kept on the row, so a "close" vs "far" river match can still be styled
differently later without a second pass.

Adds NEW columns rather than overwriting start_unid/end_unid, so existing
code that reads those lake-only fields keeps working unchanged:
  start_water_type / end_water_type    - "lake", "river", or None
  start_water_guid / end_water_guid    - unique_guid of whichever matched
  start_water_dist_m / end_water_dist_m

Wiring bwca_graph.py / graph_map.py / build_paddle_edges.js to actually READ
these new fields for routing is a separate step - this script only produces
the data (same staged approach already used for burn-area integration).

Writes a NEW file; does not overwrite portages_final.parquet.
"""
import geopandas as gpd
import pandas as pd

PORTAGES_IN = "../../Data/processed/portages_final.parquet"
LAKES_IN = "../../Data/processed/bwca_lakes.parquet"
RIVERS_IN = "../../Data/processed/bwca_rivers_lines.parquet"
PORTAGES_OUT = "../../Data/processed/portages_final_with_water.parquet"

LAKE_THRESHOLD_M = 50
RIVER_THRESHOLD_M = 50

# Column in bwca_rivers_lines.parquet that uniquely identifies each river
# SEGMENT (not unid_a/unid_b, which identify the lakes at its ends). Adjust
# this if the column was named something else when it was added.
RIVER_GUID_COLUMN = "unid"


def _match_endpoint(points: gpd.GeoDataFrame, rivers: gpd.GeoDataFrame, threshold_m: float):
    """Nearest river to each point, within threshold_m. Returns a DataFrame
    indexed the same as `points`, with river_guid/river_dist columns (NaN
    where nothing was within range)."""
    rivers_for_join = rivers[[RIVER_GUID_COLUMN, "geometry"]]
    matched = gpd.sjoin_nearest(
        points, rivers_for_join, max_distance=threshold_m, distance_col="river_dist"
    )
    # sjoin_nearest drops rows with no match within max_distance entirely,
    # so reindex back onto every original point to keep NaN for "no match".
    matched = matched[~matched.index.duplicated(keep="first")]
    return matched.reindex(points.index)[[RIVER_GUID_COLUMN, "river_dist"]]


def match_portage_water():
    portages = gpd.read_parquet(PORTAGES_IN)
    lakes = gpd.read_parquet(LAKES_IN)
    rivers = gpd.read_parquet(RIVERS_IN)

    if lakes.crs != rivers.crs:
        raise SystemExit(
            f"CRS mismatch: lakes is {lakes.crs}, rivers is {rivers.crs}. "
            f"Fix rivers' CRS (see fix_new_rivers.py) before matching - "
            f"a silent CRS mismatch here would produce wrong-looking "
            f"'no match found' results instead of an error."
        )
    if RIVER_GUID_COLUMN not in rivers.columns:
        raise SystemExit(
            f"'{RIVER_GUID_COLUMN}' not found in bwca_rivers_lines.parquet "
            f"(columns: {list(rivers.columns)}). Update RIVER_GUID_COLUMN "
            f"at the top of this script to match whatever it was named."
        )

    for end in ("start", "end"):
        unid_col = f"{end}_unid"
        dist_col = f"{end}_distance_m"
        water_type_col = f"{end}_water_type"
        water_guid_col = f"{end}_water_guid"
        water_dist_col = f"{end}_water_dist_m"
        coord_index = 0 if end == "start" else -1

        has_lake = portages[dist_col].notna() & (portages[dist_col] <= LAKE_THRESHOLD_M)

        portages[water_type_col] = None
        portages[water_guid_col] = None
        portages[water_dist_col] = pd.NA

        portages.loc[has_lake, water_type_col] = "lake"
        portages.loc[has_lake, water_guid_col] = portages.loc[has_lake, unid_col]
        portages.loc[has_lake, water_dist_col] = portages.loc[has_lake, dist_col]

        needs_river = ~has_lake
        if needs_river.any():
            endpoints = portages.loc[needs_river].copy()
            endpoints["geometry"] = gpd.GeoSeries(
                endpoints.geometry.apply(lambda g: g.coords[coord_index]).apply(
                    lambda xy: gpd.points_from_xy([xy[0]], [xy[1]])[0]
                ),
                crs=portages.crs,
            )
            river_matches = _match_endpoint(endpoints, rivers, RIVER_THRESHOLD_M)

            found_river = river_matches[RIVER_GUID_COLUMN].notna()
            idx = river_matches.index[found_river]
            portages.loc[idx, water_type_col] = "river"
            portages.loc[idx, water_guid_col] = river_matches.loc[idx, RIVER_GUID_COLUMN]
            portages.loc[idx, water_dist_col] = river_matches.loc[idx, "river_dist"]

        n_lake = (portages[water_type_col] == "lake").sum()
        n_river = (portages[water_type_col] == "river").sum()
        n_unmatched = portages[water_type_col].isna().sum()
        print(f"{end}: {n_lake} matched to a lake, {n_river} fell back to a river, "
              f"{n_unmatched} still unmatched (need boundary-clip-style investigation, "
              f"not a bigger threshold)")
        print(portages.head(),portages.shape,portages.index,portages.columns.to_list())
        bins = [50, 75, 100, 250, 1000, 1e9]
    um = portages[portages[f"start_water_type"].isna()]
    print(end, len(um), "unmatched;", um[f"start_distance_m"].isna().sum(), "had no lake match at all")
    print(pd.cut(um[f"start_distance_m"], bins).value_counts().sort_index())
    um = portages[portages[f"end_water_type"].isna()]
    print(end, len(um), "unmatched;", um[f"end_distance_m"].isna().sum(), "had no lake match at all")
    print(pd.cut(um[f"end_distance_m"], bins).value_counts().sort_index())

    portages.to_parquet(PORTAGES_OUT)
    print(f"Wrote {PORTAGES_OUT}")


if __name__ == "__main__":
    match_portage_water()