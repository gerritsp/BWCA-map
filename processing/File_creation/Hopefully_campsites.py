import geopandas as gpd
import pandas as pd


# ============================================================
# 1. LOAD DATA
# ============================================================

raw_campsites = gpd.read_file(
    "../../Data/Campsites/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb",
    layer="Campsites"
)

lakes = gpd.read_parquet(
    "../../Data/processed/bwca_lakes.parquet"
)

water = gpd.read_parquet(
    "../../Data/processed/bwca_waters.parquet"
)


# ============================================================
# 2. KEEP ONLY OPEN CAMPSITES
# ============================================================

print(f"Raw campsites: {len(raw_campsites)}")

campsites = raw_campsites[
    raw_campsites["STATUS"] == "open"
].copy()

print(f"Open campsites: {len(campsites)}")

EXPECTED_OPEN = len(campsites)


# ============================================================
# 3. STANDARDIZE CRS
# ============================================================

print("Campsite CRS:", campsites.crs)
print("Lake CRS:", lakes.crs)
print("Water CRS:", water.crs)

campsites = campsites.to_crs(lakes.crs)
water = water.to_crs(lakes.crs)


# ============================================================
# 4. GIVE EVERY CAMPSITE A TEMPORARY ID
# ============================================================

campsites = campsites.reset_index(drop=True)

campsites["source_id"] = campsites.index


# ============================================================
# 5. FIND NEAREST LAKE
# ============================================================

print("Assigning campsites to lakes...")

lake_matches = gpd.sjoin_nearest(
    campsites,
    lakes,
    how="left",
    max_distance=100,
    distance_col="distance_to_lake"
)

# Keep closest lake if multiple matches occur
lake_matches = (
    lake_matches
    .sort_values("distance_to_lake")
    .drop_duplicates("source_id", keep="first")
)


lake_info = lake_matches[
    [
        "source_id",
        "unique_guid",
        "fw_id",
        "distance_to_lake"
    ]
].rename(columns={
    "unique_guid": "lake_unique_guid",
    "fw_id": "lake_fw_id"
})


# ============================================================
# 6. FIND NEAREST WATER FEATURE
# ============================================================

print("Assigning campsites to rivers/intermittent water...")

water_matches = gpd.sjoin_nearest(
    campsites,
    water,
    how="left",
    max_distance=100,
    distance_col="distance_to_water"
)

# Keep closest water feature
water_matches = (
    water_matches
    .sort_values("distance_to_water")
    .drop_duplicates("source_id", keep="first")
)


water_info = water_matches[
    [
        "source_id",
        "unique_guid",
        "wb_class",
        "distance_to_water"
    ]
].rename(columns={
    "unique_guid": "water_unique_guid",
    "wb_class": "water_type"
})


# ============================================================
# 7. MERGE BOTH MATCHES BACK
# ============================================================

campsites = campsites.merge(
    lake_info,
    on="source_id",
    how="left"
)

campsites = campsites.merge(
    water_info,
    on="source_id",
    how="left"
)


# ============================================================
# 8. DETERMINE PRIMARY WATER TYPE
# ============================================================

campsites["water_type_final"] = "lake"

river_is_closer = (
    campsites["distance_to_water"]
    < campsites["distance_to_lake"]
)

campsites.loc[
    river_is_closer,
    "water_type_final"
] = "river"


# ============================================================
# 9. REMOVE THE ID THAT ISN'T THE PRIMARY WATER TYPE
# ============================================================

river_mask = campsites["water_type_final"] == "river"
lake_mask = campsites["water_type_final"] == "lake"


# River campsite → no lake ID
campsites.loc[
    river_mask,
    ["lake_unique_guid", "lake_fw_id"]
] = pd.NA


# Lake campsite → no river ID
campsites.loc[
    lake_mask,
    ["water_unique_guid", "water_type"]
] = pd.NA


# ============================================================
# 10. CREATE CAMP ID
# ============================================================

campsites["camp_id"] = (
    campsites["LAKE_NAME"].astype(str)
    + "_"
    + campsites["CSITENO"].astype(str)
)


# ============================================================
# 11. VALIDATION
# ============================================================

print()
print("========== VALIDATION ==========")

print("Expected open campsites:", EXPECTED_OPEN)
print("Final campsites:", len(campsites))
print("Unique source IDs:", campsites["source_id"].nunique())

print()
print("Water type:")
print(campsites["water_type_final"].value_counts(dropna=False))

print()
print("Lake IDs:", campsites["lake_unique_guid"].notna().sum())
print("Water IDs:", campsites["water_unique_guid"].notna().sum())

print()
print("Missing geometry:", campsites.geometry.isna().sum())

print("================================")


# ============================================================
# 12. SAVE
# ============================================================

campsites = campsites[
    [
        "camp_id",
        "CSITENO",
        "STATUS",
        "LAKE_NAME",

        "lake_unique_guid",
        "lake_fw_id",
        "distance_to_lake",

        "water_unique_guid",
        "water_type",
        "distance_to_water",

        "water_type_final",

        "geometry"
    ]
]

print(
    campsites[
        [
            "CSITENO",
            "LAKE_NAME",
            "water_type_final",
            "distance_to_lake",
            "distance_to_water",
            "lake_unique_guid",
            "water_unique_guid"
        ]
    ].head(20)
)
print(
    campsites[
        campsites["water_type_final"] == "river"
    ][
        [
            "CSITENO",
            "LAKE_NAME",
            "distance_to_lake",
            "distance_to_water",
            "water_unique_guid",
            "water_type"
        ]
    ].head(100)
)
campsites["water_assignment_distance"] = campsites[
    ["distance_to_lake", "distance_to_water"]
].min(axis=1)
campsites["water_distance_difference"] = (
    campsites["distance_to_lake"]
    - campsites["distance_to_water"]
).abs()
campsites.to_parquet(
    "../../Data/processed/bwca_campsites_river.parquet"
)
#
# print()
# print("Saved bwca_campsites.parquet")
suspect = campsites[campsites["distance_to_lake"].isna() & (campsites["water_type_final"] == "lake")]
print(len(suspect))
print(suspect[["CSITENO", "LAKE_NAME", "distance_to_water"]])