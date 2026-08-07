import geopandas as gpd

entries = gpd.read_parquet("../Data/processed/entry_points_joined.parquet")
portages = gpd.read_parquet("../Data/processed/portages_final.parquet")
# knife = portages[
#     (portages["lake1"].str.contains("Knife", case=False, na=False)) |
#     (portages["lake2"].str.contains("Knife", case=False, na=False))
# ]

# print(knife[["usfsid", "lake1", "lake2", "start_fw_id", "end_fw_id"]])
# print(portages.columns.tolist())
# print(portages.crs.to_epsg())
# print(portages.geometry.geom_type.unique())
print(portages.crs)
print(portages.geometry.iloc[0])
# print(entries.head())