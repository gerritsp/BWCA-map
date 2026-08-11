from models.bwca_graph import bwca_graph

graph = bwca_graph()

# -----------------------------
# Load data
# -----------------------------

graph.load_lakes("Data/processed/bwca_lakes.parquet")
graph.load_campsites("Data/processed/bwca_campsites.parquet")
graph.load_portages("Data/processed/portages_final.parquet")
graph.load_entry_points("Data/processed/entry_points_joined.parquet")
graph.connect()

unresolved = [p for p in graph.portages.values() if p.lake_a is None or p.lake_b is None]
same_lake = [p for p in graph.portages.values() if p.lake_a and p.lake_b and p.lake_a is p.lake_b]

print(f"{len(unresolved)} / {len(graph.portages)} portages have at least one unresolved endpoint")
print(f"{len(same_lake)} portages resolved to the SAME lake on both ends")

for p in same_lake[:5]:
    print(p.portage_num, p.name, "->", p.lake_a.fw_id, p.lake_a.name)
# print("Loaded:")
# print(f"Lakes:        {len(graph.lakes)}")
# print(f"Campsites:   {len(graph.campsites)}")
# print(f"Portages:    {len(graph.portages)}")
# print(f"EntryPoints: {len(graph.entry_points)}")



# -----------------------------
# Connect everything
# -----------------------------
# entry = next(iter(graph.entry_points.values()))
#
# print(entry.code)
# print(entry.fw_id)
# print(entry.name)
# graph.connect_campsites()
# graph.connect_portages()
# count = 0
#
#
# graph.connect_entry_points()
# connected = 0
#
# for e in graph.entry_points.values():
#     if hasattr(e, "lake"):
#         connected += 1
#
# print(connected)
# matched_a = 0
# matched_b = 0
#
# for p in graph.portages.values():
#     if graph.lakes.get(p.fw_id_a) is not None:
#         matched_a += 1
#
#     if graph.lakes.get(p.fw_id_b) is not None:
#         matched_b += 1
#
# print("Lake A matches:", matched_a)
# print("Lake B matches:", matched_b)
# print(type(next(iter(graph.lakes.keys()))))
# #
# # p = next(iter(graph.portages.values()))
# # print(type(p.fw_id_a))
# # print(type(p.fw_id_b))
# # print(p.fw_id_a)
# # print(p.fw_id_b)
# # print(len(graph.lakes))
# # print(len(graph.campsites))
# # print(len(graph.portages))
# # print(len(graph.entry_points))
# lake = graph.find_lake_by_name("Brule Lake")
#
# print(lake.name)
# print(len(lake.campsites))
# print(len(lake.portages))
# print(len(lake.entry_points))
# missing = 0

# for p in graph.portages.values():
#     if p.lake_a is None or p.lake_b is None:
#         missing += 1
#
# print(missing)
# print("\nConnections complete.\n")
#
# # -----------------------------
# # Campsites
# # -----------------------------

# camp_total = sum(len(l.campsites) for l in graph.lakes.values())
#
# print(f"Campsites attached: {camp_total}")
#
# # -----------------------------
# # Portages
# # -----------------------------
#
# portage_total = sum(len(l.portages) for l in graph.lakes.values())
#
# print(f"Lake-portage references: {portage_total}")
#
# # remember every successful portage belongs to TWO lakes
#
# connected_portages = sum(
#     1
#     for p in graph.portages.values()
#     if getattr(p, "lake_a", None) is not None
#     and getattr(p, "lake_b", None) is not None
# )
#
# print(f"Fully connected portages: {connected_portages}")
#
# # -----------------------------
# # Entry Points
# # -----------------------------
#
# entry_total = sum(len(l.entry_points) for l in graph.lakes.values())
#
# print(f"Entry points attached: {entry_total}")
#
# # -----------------------------
# # Sample lake
# # -----------------------------
#
# print("\nExample lake:\n")
#
# lake = graph.find_lake_by_name("Basswood")
#
# if lake:
#
#     print(lake.name)
#     print("Campsites:", len(lake.campsites))
#     print("Portages :", len(lake.portages))
#     print("Entries  :", len(lake.entry_points))
#
# # -----------------------------
# # Sample portage
# # -----------------------------
#
# print("\nExample portage:\n")
#
# p = graph.portages.get(6008)
#
# if p:
#
#     print("USFS:", p.usfs_id)
#
#     if p.lake_a:
#         print("Lake A:", p.lake_a.name)
#
#     if p.lake_b:
#         print("Lake B:", p.lake_b.name)
#
# # -----------------------------
# # Sample entry point
# # -----------------------------
#
# print("\nExample entry point:\n")
#
# ep = graph.find_entry_point("16")
#
# if ep:
#
#     print(ep.name)
#
#     if ep.lake:
#         print("Lake:", ep.lake.name)
# print("\nLakes with lots of data:\n")
#
# for lake in graph.lakes.values():
#
#     if (
#         len(lake.campsites)
#         or len(lake.portages)
#         or len(lake.entry_points)
#     ):
#
#         print(
#             f"{lake.name:25}"
#             f" Camps:{len(lake.campsites):3}"
#             f" Portages:{len(lake.portages):3}"
#             f" Entries:{len(lake.entry_points):2}"
#         )