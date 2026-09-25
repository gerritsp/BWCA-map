"""
Snaps portage endpoints to their matched lake's boundary when the endpoint is
close (<=100m) but not touching - likely imprecise trail survey data, not a
wrong-lake match (see the CLAUDE.md/session notes: anything in the
kilometers-away range is a boundary-clip issue, a totally different problem,
and should NOT be snapped - it would draw a nonsensical line across unrelated
lakes). Endpoints beyond SNAP_THRESHOLD_M are left untouched.

Writes a NEW file rather than overwriting portages_final.parquet, and adds
start_snapped/end_snapped boolean columns so the map can render snapped
portages differently from real, unmodified survey geometry - snapping an
endpoint is an algorithmic correction, not ground truth, and the map should
say so rather than presenting it as identical to a surveyed line.
"""
import geopandas as gpd
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

SNAP_THRESHOLD_M = 75

PORTAGES_IN = "../../Data/processed/portages_final.parquet"
LAKES_IN = "../../Data/processed/bwca_lakes.parquet"
PORTAGES_OUT = "../../Data/processed/portages_final_snapped.parquet"


def snap_portages():
    portages = gpd.read_parquet(PORTAGES_IN)
    lakes = gpd.read_parquet(LAKES_IN)
    lakes_by_guid = lakes.set_index("unique_guid")

    portages["start_snapped"] = False
    portages["end_snapped"] = False

    n_snapped_start = 0
    n_snapped_end = 0
    n_skipped_too_far = 0

    for idx, row in portages.iterrows():
        coords = list(row.geometry.coords)
        changed = False

        start_dist = row["start_distance_m"]
        end_dist = row["end_distance_m"]

        if 0 < start_dist <= SNAP_THRESHOLD_M and row["start_unid"] in lakes_by_guid.index:
            lake_geom = lakes_by_guid.loc[row["start_unid"], "geometry"]
            start_pt = Point(coords[0])
            _, snapped_pt = nearest_points(start_pt, lake_geom.boundary)
            coords[0] = (snapped_pt.x, snapped_pt.y)
            portages.at[idx, "start_snapped"] = True
            changed = True
            n_snapped_start += 1
        elif start_dist > SNAP_THRESHOLD_M:
            n_skipped_too_far += 1

        if 0 < end_dist <= SNAP_THRESHOLD_M and row["end_unid"] in lakes_by_guid.index:
            lake_geom = lakes_by_guid.loc[row["end_unid"], "geometry"]
            end_pt = Point(coords[-1])
            _, snapped_pt = nearest_points(end_pt, lake_geom.boundary)
            coords[-1] = (snapped_pt.x, snapped_pt.y)
            portages.at[idx, "end_snapped"] = True
            changed = True
            n_snapped_end += 1
        elif end_dist > SNAP_THRESHOLD_M:
            n_skipped_too_far += 1

        if changed:
            portages.at[idx, "geometry"] = LineString(coords)

    portages.to_parquet(PORTAGES_OUT)

    print(f"Snapped {n_snapped_start} start endpoints, {n_snapped_end} end endpoints")
    print(f"Skipped {n_skipped_too_far} endpoints beyond {SNAP_THRESHOLD_M}m "
          f"(left untouched - likely boundary-clip cases, not survey imprecision)")
    print(f"Wrote {PORTAGES_OUT}")
    print()
    print("To use this file and show snapped portages differently on the map:")
    print("1. Point build_graph()'s graph.load_portages(...) at portages_final_snapped.parquet")
    print("2. In portages_geojson(), add these two lines to the properties dict:")
    print('     "start_snapped": [bool(p.start_snapped) for p in portages],')
    print('     "end_snapped": [bool(p.end_snapped) for p in portages],')
    print("   (requires start_snapped/end_snapped to also be read in load_portages()")
    print("   and stored on the Portage object, same pattern as your other fields)")
    print("3. In js_template.js's portagesLayer style function, use a distinct")
    print("   style when either flag is true, e.g.:")
    print("     style: (feature) => (feature.properties.start_snapped || feature.properties.end_snapped)")
    print('       ? { color: "#7c3aed", weight: 3, opacity: 0.9, dashArray: "4 2" }  // snapped: purple dashed')
    print("       : PORTAGE_STYLE,  // real survey geometry: normal green")
    print("   and mention it in the popup, e.g. add a line when either flag is true:")
    print('     `<span style="color:#7c3aed;font-size:11px;">Endpoint adjusted \u2014 not surveyed</span><br>`')


if __name__ == "__main__":
    snap_portages()