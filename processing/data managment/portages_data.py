import geopandas as gpd
import pyogrio
import pandas as pd
from shapely.geometry import LineString
from models.Lake import Lake
from shapely.geometry import Point
import re

layers = gpd.list_layers("../../Data/thegpx_files_raw/Boundary Waters Canoe Area.gpx")

# print(layers)
wpts = gpd.read_file(
    "../../Data/thegpx_files_raw/Boundary Waters Canoe Area.gpx",
    layer="waypoints"
)
# layers = pyogrio.list_layers(
#     "../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb"
# )


boundary = gpd.read_file(
    "../../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb",
    layer="boundary_waters_canoe_area_wilderness"
)
lakes = gpd.read_parquet("../../Data/processed/bwca_lakes.parquet")


def parse_comment(comment):
    data = {}

    for line in comment.splitlines():

        if ":" not in line:
            continue

        key, value = line.split(":", 1)

        data[key.strip()] = value.strip()

    return data
# print(wpts.columns)
# print(len(wpts))
# print(wpts.head())
# print(wpts[["name", "sym", "type", "desc", "cmt"]].head(30))
# print(wpts["sym"].value_counts())
# print(wpts["type"].value_counts())
portages = wpts[
    wpts["name"].str.startswith("Portage ", na=False)
].copy()
# print(portages.info())
# print(f"Total portage waypoints: {len(portages)}")
# print(portages["name"].head(20).tolist())
# print(portages.isnull().sum())
# duplicates = portages["name"].duplicated().sum()
# print("Duplicate names:", duplicates)
# print(portages.geometry.is_empty.sum())
# print(portages.geometry.isna().sum())
inside = portages.within(boundary.geometry.iloc[0])
#
# print("Inside:", inside.sum())
# print("Outside:", (~inside).sum())
# print(portages.crs)
# print(boundary.crs)
# print(portages.iloc[0]["cmt"])
# print(portages["fw_id_a"].isna().sum())
# print(portages["fw_id_b"].isna().sum())
# print(portages["dist_lake_a"].describe())
# print(portages["dist_lake_b"].describe())
# print(portages["rods"].describe())
# numbers = (
#     portages["name"]
#     .str.extract(r"Portage (\d+)")[0]
#     .astype(int)
# )
#
# print(numbers.min())
# print(numbers.max())
# print(numbers.nunique())
# ids = portages["cmt"].str.extract(r"USFS ID:\s*(\d+)")[0]
#
# print(ids.nunique())

parsed = parse_comment(portages.iloc[0]["cmt"])

start_lat, start_lon = map(float, parsed["Start"].split(","))
end_lat, end_lon = map(float, parsed["End"].split(","))

record = {
    "name": portages.iloc[0]["name"],
    "waterbody": parsed["Waterbody"],
    "usfs_id": int(parsed["USFS ID"]),
    "rods": float(parsed["Rods"]),
    "start_lat": start_lat,
    "start_lon": start_lon,
    "end_lat": end_lat,
    "end_lon": end_lon
}

# print(record)
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
# print(len(records))
portage_df = pd.DataFrame(records)
# print(portage_df.head())
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
print(start_gdf.crs)
print(lakes.crs)
start_join = gpd.sjoin_nearest(
    start_gdf,
    lakes[["fw_id", "geometry"]],
    how="left",
    distance_col="distance_m"
)

end_join = gpd.sjoin_nearest(
    end_gdf,
    lakes[["fw_id", "geometry"]],
    how="left",
    distance_col="distance_m"
)
# print(start_join["fw_id"].isna().sum())
# print(end_join["fw_id"].isna().sum())
# # print(lakes.geom_type.value_counts())
# # print(lakes.columns)
# # print(lakes.head())
# # print(start_join["distance_m"].describe())
# print((start_join["distance_m"] < 25).sum())
# print((start_join["distance_m"] < 50).sum())
# print((start_join["distance_m"] < 100).sum())
records = []

for portage_num, group in portages.groupby("portage_num"):

    # Every physical portage should have exactly two rows
    if len(group) != 2:
        print(f"Skipping Portage {portage_num}: expected 2 rows, found {len(group)}")
        continue

    row1 = group.iloc[0]
    row2 = group.iloc[1]

    # Create a line connecting the two landings
    line = LineString([
        (row1.start_lon, row1.start_lat),
        (row1.end_lon, row1.end_lat)
    ])

    # Confidence rating
    max_distance = max(row1.distance_m, row2.distance_m)

    if max_distance <= 10:
        quality = "excellent"
    elif max_distance <= 25:
        quality = "good"
    elif max_distance <= 100:
        quality = "fair"
    else:
        quality = "poor"

    records.append({
        "portage_num": portage_num,
        "usfs_id": row1.usfs_id,
        "rods": row1.rods,

        "start_lat": row1.start_lat,
        "start_lon": row1.start_lon,
        "end_lat": row1.end_lat,
        "end_lon": row1.end_lon,

        "fw_id_a": row1.fw_id,
        "fw_id_b": row2.fw_id,

        "distance_a_m": row1.distance_m,
        "distance_b_m": row2.distance_m,

        "quality": quality,

        "geometry": line,
        "max_distance_m": max(row1.distance_m, row2.distance_m),
        "uncertain": max_distance > 25
    })

portages_clean = gpd.GeoDataFrame(
    records,
    geometry="geometry",
    crs="EPSG:4326"
)

output_path = "Data/Processed/processed_portages_interim.parquet"

portages_clean.to_parquet(output_path)

print(f"\nSaved {len(portages_clean)} portages")
print(output_path)