import geopandas as gpd

entries = gpd.read_parquet("../Data/entry_raw/entry_points.parquet")
portages = gpd.read_parquet("../Data/portages_raw/portages.parquet")
mine = gpd.read_parquet("../Data/portages_raw/processed_portages_interim.parquet")
final_portage = gpd.read_parquet("../Data/processed/portages_final.parquet")
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


print(entries.columns.tolist())