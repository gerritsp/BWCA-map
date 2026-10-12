import geopandas as gpd
rivers = gpd.read_file("../../Data/processed/old/bwca_river_lines.gpkg")
rivers2 = gpd.read_parquet("../../Data/processed/bwca_rivers_lines.parquet")
rivers = rivers.to_crs("EPSG:26915")
rivers.loc[rivers["river_id"] == 9999, "routable"] = True
new_row = rivers[rivers["river_id"] == 9999]
print(new_row.columns.tolist())
print(new_row.values.tolist())



print(new_row.geometry.total_bounds)
rivers.to_parquet(
    "../../Data/processed/bwca_rivers_lines.parquet",
    index=False
)
