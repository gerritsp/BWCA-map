import geopandas as gpd

entries = gpd.read_parquet("../Data/entry_raw/entry_points.parquet")  # or wherever the raw source is
bwca_lakes = gpd.read_parquet("../Data/Processed/bwca_lakes.parquet")
final_entries = gpd.read_parquet("../Data/Processed/entry_points_joined.parquet")

entries = entries.to_crs(bwca_lakes.crs)

entries_joined = gpd.sjoin_nearest(
    entries,
    bwca_lakes[["fw_id", "unique_guid", "geometry"]],
    how="left",
    distance_col="distance_to_lake"
).rename(columns={"unique_guid": "lake_unid"})
# entries_joined = entries_joined["id","name","code","longitude","latitude","fw_id","lake_unid","distace_to_lake"]
print(entries_joined.info())
print(final_entries.info())
entries_joined.to_parquet("../Data/processed/entry_points_joined.parquet")