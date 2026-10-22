import geopandas as gpd
rivers = gpd.read_parquet("../../Data/processed/bwca_rivers_lines.parquet")
print(rivers[rivers["name"] == "peter river"].values.tolist())

p = gpd.read_parquet("../../Data/processed/portages_final_with_water.parquet")
lakes = gpd.read_parquet("../../Data/processed/bwca_lakes.parquet")[["unique_guid", "pw_basin_name"]]
far = p[p["start_water_type"].isna() & (p["start_distance_m"] > 250)]
far = far.merge(lakes, left_on="start_unid", right_on="unique_guid", how="left")
print(far[["name", "lake1", "pw_basin_name", "start_distance_m"]]
      .sort_values("start_distance_m").to_string())
far.to_file("far_unmatched_starts.gpkg", driver="GPKG")