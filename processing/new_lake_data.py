import geopandas as gpd

gasket = gpd.read_file("../Data/Lakes/test.gpkg")
#
# print(gasket.crs)
# print(gasket.columns.tolist())
# print(gasket[["fw_id", "unique_id", "map_label", "acres", "shore_mi"]])
gasket = gasket.to_crs("EPSG:26915")



print("Gasket:")
print(gasket[["fw_id", "unique_id", "map_label", "acres", "shore_mi"]])
print(gasket.crs)
# Make sure we're writing the complete 4,515-lake dataset
print("Number of lakes:", len(gasket))
print("Gasket:", len(gasket[gasket["map_label"] == "Gasket"]))

# Write updated lake dataset
gasket.to_parquet("../Data/processed/bwca_lakes.parquet", index=False)

print("Lake parquet updated successfully.")