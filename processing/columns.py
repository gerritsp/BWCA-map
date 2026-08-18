import geopandas as gpd

entries = gpd.read_parquet("../Data/processed/entry_points_joined.parquet")
portages = gpd.read_parquet("../Data/processed/portages_final.parquet")
waters = gpd.read_parquet("../Data/processed/bwca_waters.parquet")
new_campsites = gpd.read_parquet("../Data/processed/bwca_campsites_river.parquet")
rivers =gpd.read_parquet("../Data/processed/bwca_rivers_lines.parquet")
# knife = portages[
#     (portages["lake1"].str.contains("Knife", case=False, na=False)) |
#     (portages["lake2"].str.contains("Knife", case=False, na=False))
# ]

# print(knife[["usfsid", "lake1", "lake2", "start_fw_id", "end_fw_id"]])
# print(portages.columns.tolist())
# print(portages.crs.to_epsg())
# print(portages.geometry.geom_type.unique())
# print(portages.crs)
# print(portages.geometry.iloc[0])
# print(rivers.head())
# print(rivers.info())
# print(rivers.shape)
# print(new_campsites.info())
# print(entries.head())
# print(len(rivers), rivers["routable"].sum())
# print(rivers["unid_a"].notna().sum(), rivers["unid_b"].notna().sum())
connector_rows = rivers[rivers["strm_type"] == "Connector (Lake)"]
print("Connector (Lake) segments total:", len(connector_rows))
print("...with unid_a resolved:", connector_rows["unid_a"].notna().sum())
print("...with unid_b resolved:", connector_rows["unid_b"].notna().sum())