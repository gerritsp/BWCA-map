import geopandas as gpd
import numpy as np
raw_campsites = gpd.read_file("../../Data/Campsites/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb", layer="Campsites")
processed = gpd.read_parquet("../../Data/processed/old/bwca_campsites.parquet")
lakes = gpd.read_parquet("../../Data/processed/bwca_lakes.parquet")
rivers = gpd.read_parquet("../../Data/processed/old/bwca_rivers.parquet")
water = gpd.read_parquet("../../Data/processed/bwca_waters.parquet")

# ============================================================
# 2. KEEP ONLY OPEN CAMPSITES
# ============================================================

print(f"Raw campsites: {len(raw_campsites)}")

campsites = raw_campsites[
    raw_campsites["STATUS"] == "open"
].copy()

print(f"Open campsites: {len(campsites)}")

# This should be 1947 with the current dataset
EXPECTED_OPEN = len(campsites)


# ============================================================
# 3. CRS
# ============================================================

print("Campsite CRS:", campsites.crs)
print("Lake CRS:", lakes.crs)

campsites = campsites.to_crs(lakes.crs)

# Make sure all water layers use the same CRS
water = water.to_crs(lakes.crs)
rivers = rivers.to_crs(lakes.crs)
campsites = campsites.to_crs(lakes.crs)

# ============================================================
# 4. ASSIGN CAMPSITES TO LAKES
# ============================================================

print("Assigning campsites to lakes...")
campsites = campsites.reset_index(drop=True)
campsites["source_id"] = campsites.index
lake_matches = gpd.sjoin_nearest(
    campsites,
    lakes,
    how="left",
    distance_col="distance_to_lake"
)
lake_matches = (
    lake_matches
    .sort_values("distance_to_lake")
    .drop_duplicates("source_id", keep="first")
)

# ------------------------------------------------------------
# IMPORTANT:
# sjoin_nearest can produce multiple rows for one campsite.
# Keep only the closest match.
# ------------------------------------------------------------

# ============================================================
# 5. KEEP LAKE INFORMATION
# ============================================================

lake_matches = lake_matches[
    [
        "source_id",
        "CSITENO",
        "STATUS",
        "geometry",
        "fw_id",
        "unique_guid",
        "map_label",
        "acres",
        "shore_mi",
        "distance_to_lake"
    ]
].rename(columns={
    "unique_guid": "lake_unique_id",
    "map_label": "lake_name",
})

print("Assigning campsites to rivers/intermittent water...")

river_matches = gpd.sjoin_nearest(
    campsites,
    rivers,
    how="left",
    distance_col="distance_to_river"
)

river_matches = (
    river_matches
    .sort_values("distance_to_river")
    .drop_duplicates("source_id", keep="first")
)
# print(
#     river_matches[
#         [
#             "source_id",
#             "CSITENO",
#             "distance_to_river"
#         ]
#     ].head()
# )
#
# print("Matched to river:", river_matches["distance_to_river"].notna().sum())
# print(
#     river_matches[
#         ["source_id", "CSITENO", "distance_to_river"]
#     ].sort_values("distance_to_river").head(50)
# )
#
# print("Matched:", river_matches["distance_to_river"].notna().sum())
# print(
#     river_matches[
#         ["source_id", "CSITENO", "distance_to_river"]
#     ]
#     .sort_values("distance_to_river")
#     .head(50)
# )
# print(river_matches["distance_to_river"].describe())
lake_distances = (
    lake_matches[
        ["source_id", "distance_to_lake"]
    ]
    .drop_duplicates("source_id")
)

river_distances = (
    river_matches[
        ["source_id", "distance_to_river"]
    ]
    .drop_duplicates("source_id")
)

campsites = campsites.merge(
    lake_distances,
    on="source_id",
    how="left"
)

campsites = campsites.merge(
    river_distances,
    on="source_id",
    how="left"
)

# Determine which water feature is closer
campsites["water_type"] = np.where(
    campsites["distance_to_lake"] <= campsites["distance_to_river"],
    "lake",
    "river"
)

# print(campsites["water_type"].value_counts())
# river_candidates = campsites[
#     campsites["distance_to_river"] < 100
# ].sort_values("distance_to_river")
#
# print(
#     river_candidates[
#         [
#             "source_id",
#             "CSITENO",
#             "LAKE_NAME",
#             "distance_to_lake",
#             "distance_to_river"
#         ]
#     ]
# )
# print("Within 10m:", (campsites["distance_to_river"] <= 10).sum())
# print("Within 25m:", (campsites["distance_to_river"] <= 25).sum())
# print("Within 50m:", (campsites["distance_to_river"] <= 50).sum())
# print("Within 100m:", (campsites["distance_to_river"] <= 100).sum())
# print(
#     river_matches[
#         [
#             "source_id",
#             "CSITENO",
#             "unique_id",
#             "wb_class",
#             "distance_to_river"
#         ]
#     ]
#     .sort_values("distance_to_river")
#     .head(50)
# )
river_camps = campsites[
    campsites["water_type"] == "river"
].copy()

print(river_camps[
    [
        "source_id",
        "CSITENO",
        "LAKE_NAME",
        "distance_to_lake",
        "distance_to_river"
    ]
].sort_values("distance_to_river"))
# print("Potential river camps:", len(river_camps))
campsites["water_type"] = np.where(
    campsites["distance_to_lake"] <= campsites["distance_to_river"],
    "lake",
    "river"
)
# river_camps = campsites[
#     campsites["distance_to_river"] < campsites["distance_to_lake"]
# ].copy()

# print(river_camps[
#     [
#         "source_id",
#         "CSITENO",
#         "distance_to_lake",
#         "distance_to_river",
#         # "river_unique_id",
#         # "river_wb_class"
#     ]
# ].sort_values("distance_to_river"))