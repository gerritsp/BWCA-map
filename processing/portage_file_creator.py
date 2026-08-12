import geopandas as gpd
import pyogrio
import pandas as pd
from shapely.geometry import LineString
from models.Lake import Lake
from shapely.geometry import Point
import re

layers = gpd.list_layers("../Data/thegpx_files_raw/Boundary Waters Canoe Area.gpx")

# print(layers)
wpts = gpd.read_file(
    "../Data/thegpx_files_raw/Boundary Waters Canoe Area.gpx",
    layer="waypoints"
)
layers = pyogrio.list_layers(
    "../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb"
)


boundary = gpd.read_file(
    "../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb",
    layer="boundary_waters_canoe_area_wilderness"
)
lakes = gpd.read_parquet("../Data/processed/bwca_lakes.parquet")

def parse_comment(comment):
    data = {}

    for line in comment.splitlines():

        if ":" not in line:
            continue

        key, value = line.split(":", 1)

        data[key.strip()] = value.strip()

    return data
portages = wpts[
    wpts["name"].str.startswith("Portage ", na=False)
].copy()


inside = portages.within(boundary.geometry.iloc[0])

parsed = parse_comment(portages.iloc[0]["cmt"])

start_lat, start_lon = map(float, parsed["Start"].split(","))
end_lat, end_lon = map(float, parsed["End"].split(","))

records = []
for _, row in portages.iterrows():

    parsed = parse_comment(row["cmt"])

    start_lat, start_lon = map(float, parsed["Start"].split(","))
    end_lat, end_lon = map(float, parsed["End"].split(","))

    records.append({
        "name": row["name"],
        "usfs_id": int(parsed["USFS ID"]),
        "rods": float(parsed["Rods"]),
        "start_lat": start_lat,
        "start_lon": start_lon,
        "end_lat": end_lat,
        "end_lon": end_lon
    })
portage_df = pd.DataFrame(records)

start_gdf = gpd.GeoDataFrame(
    portage_df.copy(),
    geometry=gpd.points_from_xy(
        portage_df.start_lon,
        portage_df.start_lat
    ),
    crs="EPSG:4326"
)

end_gdf = gpd.GeoDataFrame(
    portage_df.copy(),
    geometry=gpd.points_from_xy(
        portage_df.end_lon,
        portage_df.end_lat
    ),
    crs="EPSG:4326"
)
start_gdf = start_gdf.to_crs(lakes.crs)
end_gdf = end_gdf.to_crs(lakes.crs)
start_join = gpd.sjoin_nearest(
    start_gdf,
    lakes[["fw_id","unique_guid", "geometry"]],
    how="left",
    distance_col="distance_m"
)

end_join = gpd.sjoin_nearest(
    end_gdf,
    lakes[["fw_id", "unique_guid","geometry"]],
    how="left",
    distance_col="distance_m"
)
# print(len(start_gdf))
# print(len(start_join))
# print(start_join.index.duplicated().sum())
# print(start_join.index.value_counts().head(20))
start_join = start_join[~start_join.index.duplicated(keep="first")]
end_join = end_join[~end_join.index.duplicated(keep="first")]
portage_df["start_fw_id"] = start_join["fw_id"].values
portage_df["start_unid"] = start_join["unique_guid"].values
portage_df["start_distance_m"] = start_join["distance_m"].values

portage_df["end_fw_id"] = end_join["fw_id"].values
portage_df["end_unid"] = end_join["unique_guid"].values
portage_df["end_distance_m"] = end_join["distance_m"].values

# duplicates = start_join[start_join.index.duplicated(keep=False)]
#
# print(duplicates[["fw_id", "distance_m"]].head(20))
# print(lakes[lakes["fw_id"] == 88888][
#     ["fw_id", "map_label", "pw_basin_name", "wb_class", "acres"]
# ])
# duplicates = start_join[start_join.index.duplicated(keep=False)]
#
# print(duplicates["fw_id"].value_counts().head(20))



records = []
portage_df["portage_num"] = (
    portage_df["name"]
        .str.extract(r"Portage (\d+)")
        .astype(int)
)
print(portage_df[["name", "portage_num"]].head())
portages_clean = portage_df[
    portage_df["name"].str.contains(r"\(A to B\)")
].copy()
portages_clean["max_distance_m"] = (
    portages_clean[
        ["start_distance_m", "end_distance_m"]
    ].max(axis=1)
)
portages_clean["uncertain"] = (
    portages_clean["max_distance_m"] > 25
)
portages_clean["geometry"] = portages_clean.apply(
    lambda r: LineString([
        (r.start_lon, r.start_lat),
        (r.end_lon, r.end_lat)
    ]),
    axis=1
)
portages_clean = gpd.GeoDataFrame(
    portages_clean,
    geometry="geometry",
    crs="EPSG:4326"
)

output_path = "../Data/portages_raw/processed_portages_interim.parquet"

portages_clean.to_parquet(output_path)

print(f"\nSaved {len(portages_clean)} portages")
print(output_path)