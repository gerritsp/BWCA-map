import geopandas as gpd

raw_campsites = gpd.read_file(
    "../Data/Campsites/USFS R09 SNF BWCA Wilderness Campsites Public fgdb.gdb",
    layer="Campsites"
)
bwca_lakes = gpd.read_parquet("../Data/Processed/bwca_lakes.parquet")

raw_campsites = raw_campsites.to_crs(bwca_lakes.crs)
raw_campsites = raw_campsites[raw_campsites["STATUS"] == "open"]

campsites = gpd.sjoin_nearest(
    raw_campsites,
    bwca_lakes,
    how="left",
    distance_col="distance_to_lake"
)

campsites["camp_id"] = campsites["LAKE_NAME"] + "_" + campsites["CSITENO"].astype(str)

campsites = campsites[
    [
        "camp_id", "CSITENO", "LAKE_NAME", "map_label", "fw_id", "unique_guid",
        "STATUS", "District", "acres", "shore_mi", "distance_to_lake", "geometry"
    ]
].rename(columns={"unique_guid": "lake_unid"})

campsites.to_parquet("../Data/Processed/bwca_campsites.parquet")