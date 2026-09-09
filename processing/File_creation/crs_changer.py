import geopandas as gpd
portages = gpd.read_parquet("../../Data/processed/portages_final.parquet")
correct = gpd.read_parquet("../../Data/processed/old/portages_final_crs.parquet")
print(correct.crs)
portages = portages.to_crs("EPSG:26915")
print(portages.crs)
portages.to_parquet("../../Data/processed/portages_final.parquet")