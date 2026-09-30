import geopandas as gpd
lines = gpd.read_parquet("../../Data/processed/bwca_rivers_lines.parquet")
lines.loc[lines["name"] == "peter river", "routable"] = True
lines.to_parquet("../../Data/processed/bwca_rivers_lines.parquet")