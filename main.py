from models.bwca_graph import bwca_graph
# print(bwca_graph)
# print(type(bwca_graph))
graph = bwca_graph()

graph.load_lakes("Data/processed/bwca_lakes.parquet")
graph.load_campsites("Data/processed/bwca_campsites.parquet")

graph.connect_campsites()


davis = graph.find_lake_by_name("Davis Lake")

print("davis" in graph.lakes_by_name)
print("davis lake" in graph.lakes_by_name)

print(graph.lakes_by_name.get("davis"))
print(graph.lakes_by_name.get("davis lake"))
#
# print(knife.name)
# print(len(knife.campsites))
# print(graph.lakes[424].name)
print(len(graph.lakes))
print(graph.lakes[424])
print(davis)
print(type(davis))
# print(davis.name)
print(graph.get_num_campsites(davis))
print(davis.campsites)

basswood = graph.find_lake_by_name("Basswood Lake")

print(basswood.name)

for camp in basswood.campsites[:10]:
    print(camp.lake_name)