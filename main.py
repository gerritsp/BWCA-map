from models.bwca_graph import bwca_graph
# print(bwca_graph)
# print(type(bwca_graph))
graph = bwca_graph()

graph.load_lakes("Data/processed/bwca_lakes.parquet")
graph.load_campsites("Data/processed/bwca_campsites.parquet")

graph.connect_campsites()

knife = graph.find_lake(3731)

davis = graph.find_lake("Davis")

print(knife.name)
print(len(knife.campsites))
print(davis.campsites)
# for lake in graph.lakes.values():
#
#     if "Davis lake" in lake.name.lower():
#
#         print(lake.name)
basswood = graph.find_lake_by_name("Basswood Lake")

print(basswood.name)

for camp in basswood.campsites[:10]:
    print(camp.lake_name)