import geopandas as gpd
lakes = gpd.read_file(
    "../Data/Lakes/water_dnr_hydrography_uncompressed.gdb",
    layer="dnr_hydro_features_all"
)
boundary = gpd.read_file(
    "../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb",
    layer="boundary_waters_canoe_area_wilderness"
)
raw_campesites = gpd.read_file(
    "../Data/Campsites/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb",
    layer="Campsites"
)

lakes = lakes[
    lakes["wb_class"] == "Lake or Pond"
]
boundary = boundary.to_crs(lakes.crs)


bwca_lakes = gpd.clip(
    lakes,
    boundary
)

raw_campesites = raw_campesites.to_crs(bwca_lakes.crs)
raw_campesites = raw_campesites[
    raw_campesites["STATUS"] == "open"
]


campsites = gpd.sjoin_nearest(
    raw_campesites,
    bwca_lakes,
    how="left",
    distance_col="distance_to_lake"
)

campsites["camp_id"] = (
    campsites["LAKE_NAME"]
    + "_"
    + campsites["CSITENO"].astype(str)
)
campsites = campsites[
    [
        "camp_id",
        "CSITENO",
        "LAKE_NAME",      # USFS name
        "map_label",      # DNR name
        "fw_id",
        "STATUS",
        "District",
        "acres",
        "shore_mi",
        "distance_to_lake",
        "geometry"
    ]
]

print(campsites.columns)
print("Total campsites:", len(campsites))
print("Matched:", campsites["fw_id"].notna().sum())
print("Missing:", campsites["fw_id"].isna().sum())
print(
    campsites[
        [
            "CSITENO",
            "LAKE_NAME",
            "fw_id"
        ]
    ].head(20)
)
print(campsites.shape[0])
print(campsites["fw_id"].isna().sum())
missing = campsites[campsites["fw_id"].isna()]

print(missing[["CSITENO", "LAKE_NAME"]])
print(f"Open campsites: {len(campsites)}")
print(f"Matched lakes: {campsites['fw_id'].notna().sum()}")
print(f"Missing lakes: {campsites['fw_id'].isna().sum()}")
print(campsites["CSITENO"].nunique())
duplicates = campsites[campsites.duplicated("CSITENO", keep=False)]

print(duplicates.sort_values("CSITENO"))
print(len(bwca_lakes))
print(len(campsites))
# expected output
# [1947 rows x 6 columns]
# 4514
# 2021
bwca_lakes.to_parquet(
    "../Data/Processed/bwca_lakes.parquet"
)

campsites.to_parquet(
    "../Data/Processed/bwca_campsites.parquet"
)