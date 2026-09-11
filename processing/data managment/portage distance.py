import geopandas as gpd

portages = gpd.read_parquet("../../Data/processed/portages_final.parquet")  # your actual filename

# whichever columns hold "distance from this endpoint to its matched lake" -
# likely named dist_lake_a/dist_lake_b, or start_distance_m/end_distance_m
print(portages.columns.tolist())
print(portages[["portage_num", "name", "start_distance_m", "end_distance_m"]]
      .sort_values("start_distance_m", ascending=False)
      .head(20))
print(portages[["portage_num", "name", "start_distance_m", "end_distance_m"]]
      .sort_values("end_distance_m", ascending=False)
      .head(20))
print(portages[portages["portage_num"] == 161].value_counts())