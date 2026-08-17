import geopandas as gpd
from shapely.geometry import Point

MAX_MATCH_DISTANCE_M = 25

ROUTABLE_TYPES = {"Centerline (River)", "Connector (River)", "Connector (Lake)"}
KEEP_TYPES = ROUTABLE_TYPES | {"Stream (Perennial)"}

rivers = gpd.read_file(
    "../../Data/Lakes/water_dnr_hydrography_uncompressed.gdb",
    layer="dnr_rivers_and_streams"
)
boundary = gpd.read_file(
    "../../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb",
    layer="boundary_waters_canoe_area_wilderness"
)
boundary = boundary.to_crs(rivers.crs)

rivers = rivers[rivers["Strm_type_desc"].isin(KEEP_TYPES)].copy()

rivers = gpd.clip(rivers, boundary)
rivers = rivers.explode(index_parts=False).reset_index(drop=True)
rivers["river_id"] = rivers.index

rivers["name"] = rivers["KITTLE_NAME"].str.strip().replace("", None)
rivers["strm_type"] = rivers["Strm_type_desc"]
rivers["routable"] = rivers["strm_type"].isin(ROUTABLE_TYPES)

# Snap endpoints to a shared node key so segments meeting at a junction
# (confluence, or a lake connector meeting a stream) resolve to the same
# graph node - see CLAUDE.md/riverCreator design notes: this network's
# adjacent segments genuinely share exact endpoint coordinates, so cheap
# coordinate-snapping is a legitimate substitute for a full topology engine.
def node_key(coord):
    return f"{coord[0]:.1f}_{coord[1]:.1f}"

rivers["node_a"] = rivers.geometry.apply(lambda g: node_key(g.coords[0]))
rivers["node_b"] = rivers.geometry.apply(lambda g: node_key(g.coords[-1]))
rivers["length_m"] = rivers.geometry.length

lakes = gpd.read_parquet("../../Data/Processed/bwca_lakes.parquet")
lakes = lakes.to_crs(rivers.crs)
lake_candidates = lakes[["fw_id","unique_guid", "geometry"]]

# Only "Connector (Lake)" endpoints are a reliable "this touches a lake"
# signal (verified: 99% within 25m, median distance 0.0m - they touch the
# polygon; other segment types are 65-74% within 25m largely by incidental
# proximity, e.g. a creek running past a pond it doesn't connect to).
# Join on UNIQUE nodes, not one row per segment-endpoint, so two segments
# sharing a snapped node can't land on different nearest lakes on a tie -
# the same silent-overwrite failure mode as the fw_id/camp_id collisions
# already documented in CLAUDE.md.
connector_lake = rivers[rivers["strm_type"] == "Connector (Lake)"]
candidate_nodes = list(set(connector_lake["node_a"]) | set(connector_lake["node_b"]))
node_coords = {}
for _, row in connector_lake.iterrows():
    node_coords[row["node_a"]] = row.geometry.coords[0]
    node_coords[row["node_b"]] = row.geometry.coords[-1]

node_pts = gpd.GeoDataFrame(
    {"node": candidate_nodes},
    geometry=[Point(node_coords[n]) for n in candidate_nodes],
    crs=rivers.crs,
)
node_match = gpd.sjoin_nearest(node_pts, lake_candidates, how="left", distance_col="dist")
node_match = node_match[~node_match.index.duplicated(keep="first")]
node_match = node_match[node_match["dist"] <= MAX_MATCH_DISTANCE_M]

node_to_fw_id = dict(zip(node_match["node"], node_match["fw_id"]))
node_to_unid = dict(zip(node_match["node"], node_match["unique_guid"]))
node_to_dist = dict(zip(node_match["node"], node_match["dist"]))

rivers["fw_id_a"] = rivers["node_a"].map(node_to_fw_id)
rivers["unid_a"] = rivers["node_a"].map(node_to_unid)
rivers["dist_lake_a"] = rivers["node_a"].map(node_to_dist)

rivers["fw_id_b"] = rivers["node_b"].map(node_to_fw_id)
rivers["unid_b"] = rivers["node_b"].map(node_to_unid)
rivers["dist_lake_b"] = rivers["node_b"].map(node_to_dist)

print("segments kept:", len(rivers))
print("routable segments:", rivers["routable"].sum())
print("nodes attached to a lake:", len(node_to_fw_id))
print("segment endpoints resolved to a lake: a=%d b=%d" % (
    rivers["fw_id_a"].notna().sum(), rivers["fw_id_b"].notna().sum()
))

rivers = rivers[[
    "river_id",
    "name",
    "strm_type",
    "routable",
    "node_a",
    "node_b",
    "fw_id_a",
    "dist_lake_a",
    "fw_id_b",
    "dist_lake_b",
    "length_m",
    "geometry",
    "unid_a",
    "unid_b"
]]

# See fileCreator.py: this source carries the same "promoted to 3D" PROJJSON
# quirk - force a clean EPSG tag before writing.
rivers = rivers.to_crs("EPSG:26915")  # NAD83 / UTM zone 15N

rivers.to_parquet("../../Data/Processed/bwca_rivers_lines.parquet")