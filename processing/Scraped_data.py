import geopandas as gpd
import json
entries = gpd.read_parquet("../Data/entry_raw/entry_points.parquet")
portages = gpd.read_parquet("../Data/portages_raw/portages.parquet")
mine = gpd.read_parquet("../Data/portages_raw/processed_portages_interim.parquet")
final_portage = gpd.read_parquet("../Data/processed/portages_final.parquet")
burn = gpd.read_parquet("../Data/processed/fires2026.parquet")
bwca = gpd.read_file("../Data/Boundaries/bdry_boundary_waters_canoe_area/bdry_boundary_waters_canoe_area.gdb", layer="boundary_waters_canoe_area_wilderness")
lakes = gpd.read_parquet("../Data/Processed/bwca_lakes.parquet")
# portages["miles"] = portages["meters"]*0.000621371
# portages["code"] = portages["code"].astype(int)
# mine["portage_num"] = mine["portage_num"].astype(int)
#
# portages["miles"] = portages["miles"].round(3)
# portages["meters"] = portages["meters"].astype(int)
#
# merged = portages.merge(
#     mine[
#         [
#             "portage_num",
#             "start_fw_id",
#             "end_fw_id",
#             "start_unid",
#             "end_unid",
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
### merged.to_parquet("../Data/processed/portages_final.parquet")
print(final_portage.info())
#
# print(fires.columns)
#
# print(fires.crs)

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
# print(fires.crs)
# print(len(burn))
# print(burn.columns.tolist())
# print(lakes.info())
# print(fires.geometry.iloc[0])
# print(lakes.geometry.iloc[0])
# print(sum(len(g.exterior.coords) if g.geom_type == "Polygon" else sum(len(p.exterior.coords) for p in g.geoms) for g in burn.geometry))
# def vertex_count(geom):
#     if geom.geom_type == "Polygon":
#         return len(geom.exterior.coords)
#     return sum(len(p.exterior.coords) for p in geom.geoms)
#
# before = sum(vertex_count(g) for g in burn.geometry)
# print("before:", before)
#
# simplified = burn.geometry.simplify(0.0003, preserve_topology=True)
# after = sum(vertex_count(g) for g in simplified)
# print("after:", after)
# burn.to_parquet("../Data/processed/fires2026_reduced.parquet")
#
# geojson = json.loads(burn.to_json())
# def round_coords(obj):
#     if isinstance(obj, list):
#         if obj and isinstance(obj[0], (int, float)):
#             return [round(x, 5) for x in obj]
#         return [round_coords(x) for x in obj]
#     return obj
#
#
# for feature in geojson["features"]:
#     feature["geometry"]["coordinates"] = round_coords(feature["geometry"]["coordinates"])


#
# print("Total lake rows:", len(lakes))
# print("Unique fw_id values:", lakes["fw_id"].nunique())
# print(mine.info())
# dupes = lakes[lakes.duplicated("fw_id", keep=False)].sort_values("fw_id")
# print(f"\n{len(dupes)} rows share a duplicated fw_id:")
# print(dupes[["fw_id", "map_label"]].to_string())
print(entries.info())
print(entries[entries["code"] == 88888])