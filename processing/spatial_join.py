import geopandas as gpd

entries = gpd.read_parquet("../Data/entry_raw/entry_points.parquet")
lakes = gpd.read_parquet("../Data/processed/bwca_lakes.parquet")
entries = entries.to_crs(lakes.crs)

joined = gpd.sjoin_nearest(
    entries,
    lakes[["fw_id", "geometry"]],
    how="left",
    distance_col="distance_m"
)
joined.to_parquet("../Data/processed/entry_points_joined.parquet")