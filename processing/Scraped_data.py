import geopandas as gpd

entries = gpd.read_parquet("../Data/entry_raw/entry_points.parquet")
portages = gpd.read_parquet("../Data/portages_raw/portages.parquet")
mine = gpd.read_parquet("../Data/portages_raw/processed_portages_interim.parquet")
final_portage = gpd.read_parquet("../Data/processed/portages_final.parquet")
fires = gpd.read_parquet("../Data/processed/fires2026.parquet")
bwca = gpd.read_file("../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb", layer="boundary_waters_canoe_area_wilderness")
# portages["miles"] = portages["meters"]*0.000621371
# portages["code"] = portages["code"].astype(int)
# mine["portage_num"] = mine["portage_num"].astype(int)
# final_portage["miles"] = final_portage["miles"].round(3)
# final_portage["meters"] = final_portage["meters"].astype(int)
# merged = portages.merge(
#     mine[
#         [
#             "portage_num",
#             "start_fw_id",
#             "end_fw_id",
#             "start_distance_m",
#             "end_distance_m",
#         ]
#     ],
#     left_on="code",
#     right_on="portage_num",
#     how="left",
#     validate="one_to_one"
# )
# merged["uncertain"] = (
#     (merged["start_distance_m"] > 25)
#     | (merged["end_distance_m"] > 25)
# )
#
# print(fires.columns)
#
# print(fires.crs)
#
# print(len(fires))
#
# print(fires.geometry.geom_type.value_counts())
#
# print(fires.head())
# print("BWCA valid:", bwca.is_valid.all())
# print("Fires valid:", fires.is_valid.all())
# bwca["geometry"] = bwca.geometry.make_valid()
# fires["geometry"] = fires.geometry.make_valid()
# bwca = bwca.to_crs(fires.crs)
#
# fires = gpd.clip(fires, bwca)
#
#
#
# fires = fires[
#     [
#         "poly_IncidentName",
#         "poly_GISAcres",
#         "poly_FeatureStatus",
#         "poly_FeatureCategory",
#         "attr_ModifiedOnDateTime_dt",
#         "geometry"
#     ]
# ].copy()
#
# fires = fires.rename(columns={
#     "poly_IncidentName": "incident_name",
#     "poly_GISAcres": "acres",
#     "poly_FeatureStatus": "status",
#     "poly_FeatureCategory": "category",
#     "attr_ModifiedOnDateTime_dt": "last_updated"
# })
# print(fires.info())
# print(fires.head())
# print(fires.crs)
# fires.to_parquet(
#     "../Data/processed/fires2026.parquet",
#     index=False
# )
# print(fires["incident_name"])
# print(fires["acres"])
print(fires.crs)
print(len(fires))
