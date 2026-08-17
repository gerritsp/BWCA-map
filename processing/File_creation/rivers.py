import geopandas as gpd

hydro = gpd.read_file("../../Data/Lakes/water_dnr_hydrography_uncompressed.gdb",layer="dnr_hydro_features_all")
boundary = gpd.read_file("../../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb",
    layer="boundary_waters_canoe_area_wilderness")
# print(hydro.columns.tolist())
rivers = hydro[hydro["wb_class"] == "Riverine polygon"].copy()
intermitten = hydro[hydro["wb_class"] == "Intermittent Water"].copy()
# boundary = boundary.to_crs(hydro.crs)
# bwca_hydro = gpd.clip(hydro, boundary)
# # print(bwca_hydro["wb_class"].value_counts())
# river_types = hydro[
#     hydro["wb_class"].isin([
#         "Riverine polygon",
#         "Intermittent Water"
#     ])
# ].copy()
#
# river_types["geometry"] = river_types.geometry.make_valid()
#
# boundary = boundary.to_crs(river_types.crs)
# boundary["geometry"] = boundary.geometry.make_valid()
#
# rivers = gpd.clip(river_types, boundary)
#
# rivers.to_parquet(
#     "../../Data/processed/bwca_rivers.parquet"
# )



# wetlands = hydro[
#     hydro["wb_class"] == "Wetland"
# ].copy()
#
# wetlands["geometry"] = wetlands.geometry.make_valid()
#
# boundary = boundary.to_crs(wetlands.crs)
# wetlands = gpd.clip(wetlands, boundary)
#
# wetlands.to_parquet(
#     "../../Data/processed/bwca_wetlands.parquet"
# )
# Innundation_Area  = hydro[
#     hydro["wb_class"] == "Innundation Area"
# ].copy()
#
# Innundation_Area["geometry"] = Innundation_Area.geometry.make_valid()
#
# boundary = boundary.to_crs(Innundation_Area.crs)
# wetlands = gpd.clip(Innundation_Area, boundary)
#
# wetlands.to_parquet(
#     "../../Data/processed/bwca_Innundation_Areas.parquet"
# )
boundary = boundary.to_crs(hydro.crs)
bwca_hydro = gpd.clip(hydro, boundary)
bwca_hydro = bwca_hydro[bwca_hydro["wb_class"] != "Island or Land"]
bwca_hydro["geometry"] = bwca_hydro.geometry.make_valid()

print(bwca_hydro.info())
bwca_hydro.to_parquet(
    "../../Data/processed/bwca_waters.parquet"
)